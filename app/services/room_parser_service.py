"""
룸 정보 파싱 서비스.

정규표현식과 키워드 규칙을 사용하여 비정형 합주실 정보를 구조화된 데이터로 변환합니다.
"""

import logging
import re
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


# 명확한 의미가 있는 키워드만 사용
KEYWORD_CAPACITY_MAP = {
    "대형": 15,
    "중형": 8,
    "소형": 4,
    "대합주실": 15,
    "소합주실": 4,
}


class RoomParserService:
    """Rule-based parser for rehearsal room information."""

    async def parse_room_desc(self, name: str, desc: str) -> Dict[str, Any]:
        """룸 이름과 설명을 기반으로 구조화된 정보를 추출합니다."""
        keyword_capacity = self._infer_capacity_from_keyword(name)
        parsed = self._parse_with_regex(name, desc)

        if keyword_capacity:
            parsed["max_capacity"] = keyword_capacity
            logger.debug("Keyword capacity applied: %s -> %s", name, keyword_capacity)

        return parsed

    async def parse_room_desc_batch(self, items: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
        """여러 룸 정보를 한 번에 파싱합니다."""
        if not items:
            return {}

        results: Dict[str, Dict[str, Any]] = {}
        for item in items:
            room_id = item["id"]
            room_desc = item.get("desc") or ""
            if not room_desc:
                room_desc = item.get("business_desc") or ""
            results[room_id] = self._parse_with_regex(item["name"], room_desc)
            keyword_capacity = self._infer_capacity_from_keyword(item["name"])
            if keyword_capacity:
                results[room_id]["max_capacity"] = keyword_capacity
        return results

    def _infer_capacity_from_keyword(self, name: str) -> Optional[int]:
        """룸 이름에서 키워드 기반으로 수용 인원을 추론합니다."""
        for keyword, capacity in KEYWORD_CAPACITY_MAP.items():
            if keyword in name:
                return capacity
        return None

    def _parse_with_regex(self, name: str, desc: Optional[str]) -> Dict[str, Any]:
        """정규표현식 기반 룸 정보 파싱."""
        desc = desc or ""

        clean_name = name
        day_type = None

        if "[평일]" in name or "(평일)" in name:
            day_type = "weekday"
        elif "[주말]" in name or "(주말)" in name or "주말/공휴일" in name:
            day_type = "weekend"
        clean_name = self._clean_room_name(clean_name)

        max_cap, rec_cap, parsed_range = self._extract_capacity_from_text(desc)
        max_cap_from_name, rec_cap_from_name, range_from_name = self._extract_capacity_from_text(name)

        if not max_cap:
            max_cap = max_cap_from_name
        if not rec_cap:
            rec_cap = rec_cap_from_name
        if not parsed_range:
            parsed_range = range_from_name
        if max_cap and not rec_cap:
            rec_cap = max_cap // 2 if max_cap > 4 else max_cap

        base_cap = None
        extra_charge = None

        base_match = re.search(r"기본\s*(\d+)", desc)
        if base_match:
            base_cap = int(base_match.group(1))

        charge_match = re.search(r"(?:1인|인당)\s*(?:추가)?.*?(\d+(?:,\d+)?)\s*원", desc)
        if charge_match:
            extra_charge = int(charge_match.group(1).replace(",", ""))

        requires_call = "당일" in desc and ("전화" in desc or "문의" in desc)

        can_reserve_1h = True
        if (
            "최소 2시간" in desc
            or "최소2시간" in desc
            or "2시간 이상" in desc
            or "2시간 이상만" in desc
            or "1시간 불가" in desc
            or "1시간 예약 불가" in desc
            or ("1시간" in desc and "불가" in desc)
        ):
            can_reserve_1h = False

        rec_range = parsed_range

        def _map_day_type(keyword: Optional[str]) -> str:
            """요일 키워드를 day_type 문자열로 매핑한다.

            Args:
                keyword: 요일 키워드 ("평일", "주말", "공휴일" 또는 None).

            Returns:
                str: "weekday" 또는 "weekend".
            """
            if keyword == "평일":
                return "weekday"
            if keyword in {"주말", "공휴일"}:
                return "weekend"
            return day_type or "weekday"

        price_config = None

        time_override_match = re.search(
            r"(평일|주말|공휴일)?\s*(\d{1,2})시\s*이후\s*(\d+(?:,\d+)?)\s*원",
            desc,
        )
        if time_override_match:
            override_day = _map_day_type(time_override_match.group(1))
            start_hour_num = int(time_override_match.group(2))
            override_price = int(time_override_match.group(3).replace(",", ""))
            if 0 <= start_hour_num <= 23:
                price_config = {
                    "default": None,
                    "overrides": [
                        {
                            "day_type": override_day,
                            "start_hour": f"{start_hour_num:02d}:00",
                            "end_hour": "24:00",
                            "price": override_price,
                        }
                    ],
                    "surcharges": [],
                }

        surcharge_match = re.search(
            r"(평일|주말|공휴일)?\s*(\d+(?:,\d+)?)\s*원\s*추가",
            desc,
        )
        if surcharge_match:
            surcharge_day = _map_day_type(surcharge_match.group(1))
            surcharge_amount = int(surcharge_match.group(2).replace(",", ""))
            if price_config is None:
                price_config = {
                    "default": None,
                    "overrides": [],
                    "surcharges": [],
                }
            price_config["surcharges"].append(
                {"day_type": surcharge_day, "amount": surcharge_amount}
            )

        return {
            "clean_name": clean_name,
            "day_type": day_type,
            "max_capacity": max_cap,
            "recommend_capacity": rec_cap,
            "recommend_capacity_range": rec_range,
            "base_capacity": base_cap,
            "extra_charge": extra_charge,
            "price_config": price_config,
            "requires_call_on_sameday": requires_call,
            "can_reserve_one_hour": can_reserve_1h,
        }

    # 시간대 구분 키워드: 태그에서 이 키워드가 감지되면 프로모 제거 후 레이블로 보존
    _TIME_SLOT_KEYWORDS = {
        "평일 낮": "평일 낮",
        "평일낮": "평일 낮",
        "평일 오전": "평일 오전",
        "평일 야간": "평일 야간",
        "평일": "평일",
        "주말": "주말",
        "공휴일": "공휴일",
        "주말/공휴일": "주말/공휴일",
        "심야": "심야",
        "야간": "야간",
        "주간": "주간",
    }

    @classmethod
    def _extract_time_slot_label(cls, tag_text: str) -> Optional[str]:
        """태그 텍스트에서 시간대 레이블을 추출한다. 긴 키워드부터 매칭."""
        lowered = tag_text.lower()
        for keyword, label in sorted(cls._TIME_SLOT_KEYWORDS.items(), key=lambda x: -len(x[0])):
            if keyword in lowered:
                return label
        return None

    @classmethod
    def _clean_room_name(cls, name: str) -> str:
        """Normalize room display name by stripping promo/policy noise."""
        clean = re.sub(r"\s+", " ", (name or "")).strip()
        if not clean:
            return clean

        # Common prefix noise: EVENT))1번방 -> 1번방
        clean = re.sub(r"^\s*(?:event|이벤트)\s*[)\]-]*\s*", "", clean, flags=re.IGNORECASE)

        # Remove day-type tags and capacity tags anywhere in name.
        clean = re.sub(r"\[평일\]|\(평일\)", " ", clean)
        clean = re.sub(r"\[주말[^\]]*\]|\(주말[^)]*\)|\[주말/공휴일\]", " ", clean)
        clean = re.sub(
            "(\\([^)]*(?:\\uc815\\uc6d0|\\ucd5c\\ub300\\s*\\uc778\\uc6d0|\\ucd5c\\ub300\\uc778\\uc6d0|\\ucd5c\\ub300)\\s*\\d+\\s*(?:\\uc778|\\uba85)[^)]*\\))",
            " ",
            clean,
        )
        clean = re.sub(
            r"\s*\(?\s*(?:정원\s*\d+\s*(?:인|명)\s*,?\s*)?(?:최대\s*\d+\s*(?:인|명))\s*\)?",
            " ",
            clean,
        )
        clean = re.sub(r"\s*\(\s*-\s*\d+\s*(?:인|명)\s*\)", " ", clean)

        # Remove leading bracket labels when they look like promo/operation notes.
        # 시간대 키워드가 포함된 태그는 레이블을 추출해서 뒤에 붙인다.
        time_slot_label: Optional[str] = None
        promo_markers = (
            "특가",
            "할인",
            "이벤트",
            "event",
            "평일",
            "주말",
            "공휴일",
            "심야",
            "야간",
            "주간",
            "요금",
            "운영",
            "한정",
            "예약",
            "문의",
            "전화",
        )
        while True:
            m = re.match(r"^\s*\[([^\]]{1,60})\]\s*", clean)
            if not m:
                break
            tag = m.group(1).strip().lower()
            if any(marker in tag for marker in promo_markers):
                if time_slot_label is None:
                    time_slot_label = cls._extract_time_slot_label(tag)
                clean = clean[m.end():].strip()
                continue
            break

        # Remove trailing parenthetical notes related to reservation/promo/time.
        note_pattern = re.compile(
            r"(예약|입금|문의|전화|필수|요망|확인|할인|특가|평일|주말|공휴일|심야|야간|주간|요금|당일|event|이벤트|정원|최대|\d+\s*%|\d{1,2}\s*시|~|원)",
            re.IGNORECASE,
        )
        while True:
            m = re.search(r"\s*\(([^)]{1,80})\)\s*$", clean)
            if not m:
                break
            note = m.group(1).strip()
            if note_pattern.search(note):
                clean = clean[:m.start()].strip()
                continue
            break

        # Guard against dangling parenthesis after partial tag stripping.
        if clean.count("(") > clean.count(")"):
            clean = re.sub(r"\([^)]*$", "", clean).strip()
        elif clean.count(")") > clean.count("("):
            clean = clean.replace(")", " ")

        clean = re.sub(r"\s+", " ", clean).strip(" -_/")
        clean = clean or (name or "").strip()

        # 시간대 레이블이 추출되었으면 이름 뒤에 붙인다.
        if time_slot_label:
            clean = f"{clean} ({time_slot_label})"

        return clean

    def _extract_capacity_from_text(
        self, text: str
    ) -> Tuple[Optional[int], Optional[int], Optional[List[int]]]:
        """텍스트에서 max/recommend capacity 및 범위를 추출합니다."""
        max_cap = None
        rec_cap = None
        capacity_range = None

        capacity_paren_match = re.search(
            r"\(\s*정원\s*(\d+)\s*(?:인|명)\s*,\s*최대\s*(\d+)\s*(?:인|명)\s*\)",
            text,
        )
        if capacity_paren_match:
            rec_cap = int(capacity_paren_match.group(1))
            max_cap = int(capacity_paren_match.group(2))
            return max_cap, rec_cap, None

        recommend_match = re.search(r"정원\s*(\d+)\s*(?:인|명)", text)
        if recommend_match:
            rec_cap = int(recommend_match.group(1))

        max_match = re.search(
            "(?:(?:\ucd5c\ub300\\s*\uc778\uc6d0|\ucd5c\ub300\uc778\uc6d0|\ucd5c\ub300)|max)\\s*(\\d+)",
            text,
            re.IGNORECASE,
        )
        if max_match:
            max_cap = int(max_match.group(1))

        if not max_cap:
            until_match = re.search(r"(\d+)\s*(?:인|명)\s*(?:까지|이하|수용)", text)
            if until_match:
                max_cap = int(until_match.group(1))

        if not max_cap:
            usage_match = re.search(
                r"(\d+)\s*(?:인|명)(?:이|이서)?\s*(?:합주|이용|수용)?\s*가능",
                text,
            )
            if usage_match:
                max_cap = int(usage_match.group(1))

        if not max_cap:
            paren_max_match = re.search(r"\(\s*-\s*(\d+)\s*(?:인|명)\s*\)", text)
            if paren_max_match:
                max_cap = int(paren_max_match.group(1))

        range_match = re.search(r"(\d+)\s*[~\-]\s*(\d+)\s*(?:인|명)", text)
        if range_match:
            min_r = int(range_match.group(1))
            max_r = int(range_match.group(2))
            rec_cap = (min_r + max_r) // 2
            capacity_range = [min_r, max_r]
            if not max_cap:
                max_cap = max_r
        elif not rec_cap and not range_match:
            space_range_match = re.search(
                r"권장\s*인원\s*(\d+)\s*(?:인|명)\s*(\d+)\s*(?:인|명)",
                text,
            )
            if space_range_match:
                min_r = int(space_range_match.group(1))
                max_r = int(space_range_match.group(2))
                rec_cap = (min_r + max_r) // 2
                capacity_range = [min_r, max_r]
                if not max_cap:
                    max_cap = max_r

        return max_cap, rec_cap, capacity_range
