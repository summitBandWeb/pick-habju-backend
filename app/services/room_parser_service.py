"""
룸 정보 파싱 서비스

Ollama 로컬 LLM을 사용하여 비정형 합주실 정보를 구조화된 데이터로 변환합니다.
LLM 파싱 실패 시 정규표현식 기반 Fallback으로 안정성을 보장합니다.

사용법:
    service = RoomParserService()
    result = await service.parse_room_desc("[평일] 블랙룸", "최대 10인")
"""

import json
import logging
import re
from typing import Dict, Any, List, Optional

from app.core.ollama_client import OllamaClient

logger = logging.getLogger(__name__)


# Level 1: Keyword Capacity Map (명확한 의미가 있는 키워드만)
# NOTE: 알파벳 한 글자(L룸, S룸, M룸)는 의도적으로 제외
#       합주실마다 의미가 다를 수 있음 (S = Small 또는 Special)
KEYWORD_CAPACITY_MAP = {
    "대형": 15,
    "중형": 8,
    "소형": 4,
    "대합주실": 15,
    "소합주실": 4,
}


# 8B 모델 최적화 프롬프트 (Few-shot 예시 포함)
# NOTE: v2.0.0 - recommend_capacity_range 추출 규칙 추가
ROOM_PARSE_PROMPT = """Extract room info as JSON.

Example 1:
Input: "[평일] 블랙룸", "최대 8명, 4~6인 권장"
Output: {{"clean_name": "블랙룸", "day_type": "weekday", "max_capacity": 8, "recommend_capacity": 5, "recommend_capacity_range": [4, 6], "base_capacity": null, "extra_charge": null, "requires_call_on_same_day": false}}

Example 2:
Input: "화이트룸", "기본 4인, 인당 3000원 추가"
Output: {{"clean_name": "화이트룸", "day_type": null, "max_capacity": null, "recommend_capacity": null, "recommend_capacity_range": null, "base_capacity": 4, "extra_charge": 3000, "requires_call_on_same_day": false}}

Example 3:
Input: "[주말] 스튜디오A", "당일 예약은 전화 문의"
Output: {{"clean_name": "스튜디오A", "day_type": "weekend", "max_capacity": null, "recommend_capacity": null, "recommend_capacity_range": null, "base_capacity": null, "extra_charge": null, "requires_call_on_same_day": true}}

Rules:
- clean_name: Remove tags like [평일], (주말) from name
- day_type: "weekday" if 평일, "weekend" if 주말/공휴일, else null
- max_capacity: Max people (number)
- recommend_capacity: Recommended people. Use mid-value for ranges (4~6 -> 5)
- recommend_capacity_range: [min, max] array from ranges like "4~6인 권장". null if no range found
- base_capacity: Base people count for pricing
- extra_charge: Extra charge per person (number only, no currency)
- requires_call_on_same_day: true if "당일" and ("전화" or "문의") found

Now extract:
Input: "{name}", "{desc}"
Output:"""


# 배치 파싱용 프롬프트
# NOTE: v2.0.0 - recommend_capacity_range 추출 규칙 추가
BATCH_PARSE_PROMPT = """Extract room info from multiple rooms as JSON object.
Keys should be the room IDs provided. Use null for missing values.

Rules:
- clean_name: Remove tags like [평일], (주말) from name
- day_type: "weekday" if 평일, "weekend" if 주말/공휴일, else null
- max_capacity: Max people (number)
- recommend_capacity: Use mid-value for ranges (4~6 -> 5)
- recommend_capacity_range: [min, max] array from ranges like "4~6인". null if no range
- base_capacity: Base people count for pricing
- extra_charge: Extra charge per person (number only)
- requires_call_on_same_day: true if "당일" and ("전화" or "문의") found

Rooms:
{rooms_text}

Output format:
{{"id1": {{"clean_name": "...", "day_type": "...", ...}}, "id2": {{...}}}}"""


class RoomParserService:
    """Ollama 로컬 LLM을 사용하여 비정형 룸 정보를 구조화된 데이터로 변환합니다.
    
    LLM 파싱 실패 시 정규표현식 기반 Fallback을 사용하여 안정성을 보장합니다.
    8B 소형 모델의 특성을 고려한 Few-shot 프롬프트를 사용합니다.
    """
    
    def __init__(self, ollama_client: Optional[OllamaClient] = None):
        """RoomParserService 초기화.
        
        Args:
            ollama_client: Ollama 클라이언트 인스턴스 (DI용)
        """
        self.ollama_client = ollama_client or OllamaClient()

    def _clean_text_for_llm(self, text: str) -> str:
        """LLM 입력 전 노이즈 제거.
        
        HTML 태그, 이모지, 특수문자를 제거하여 8B 모델이
        핵심 정보(숫자)에 집중할 수 있도록 합니다.
        """
        # 1. HTML 태그 제거
        text = re.sub(r'<[^>]+>', '', text)
        
        # 2. 이모지 제거 (한글, 영문, 숫자, 공백 및 필수 기호 ~, -, , 유지)
        text = re.sub(r'[^\w\s가-힣~\-,]', ' ', text)
        
        # 3. 연속 공백 정리
        text = re.sub(r'\s+', ' ', text)
        
        return text.strip()
    
    def _infer_capacity_from_keyword(self, name: str) -> Optional[int]:
        """룸 이름에서 키워드 기반으로 수용 인원을 즉시 추론.
        
        대형/중형/소형 등 명확한 의미가 있는 키워드만 사용합니다.
        """
        for keyword, capacity in KEYWORD_CAPACITY_MAP.items():
            if keyword in name:
                return capacity
        return None

    async def parse_room_desc(self, name: str, desc: str) -> Dict[str, Any]:
        """룸 이름과 설명을 기반으로 구조화된 정보를 추출합니다.
        
        Args:
            name: 룸 이름 (예: "[평일] 블랙룸")
            desc: 룸 설명 (예: "최대 10인, 4~6인 권장")
            
        Returns:
            파싱된 룸 정보 딕셔너리
        """
        # Level 1: Keyword Map (가장 빠름)
        keyword_capacity = self._infer_capacity_from_keyword(name)
        if keyword_capacity:
            # 키워드 매칭 성공 시 Regex로 나머지 정보 보완
            regex_result = self._parse_with_regex(name, desc)
            regex_result["max_capacity"] = keyword_capacity
            logger.debug(f"Keyword Map 성공: {name} -> max_capacity={keyword_capacity}")
            return regex_result
        
        # Level 2: Regex 시도 (max_capacity가 추출되면 성공)
        regex_result = self._parse_with_regex(name, desc)
        if regex_result.get("max_capacity"):
            logger.debug(f"Regex 파싱 성공: {name}")
            return regex_result

        # Level 3: Noise Reduction + LLM (느리지만 정확)
        clean_name = self._clean_text_for_llm(name)
        clean_desc = self._clean_text_for_llm(desc or "")

        prompt = ROOM_PARSE_PROMPT.format(
            name=clean_name,
            desc=clean_desc or "내용 없음"
        )

        # Ollama LLM 파싱 시도
        response = await self.ollama_client.generate(prompt)

        if response:
            try:
                result = self._extract_json_from_response(response)
                parsed = json.loads(result)

                # 파싱 결과 검증
                if self._validate_parsed_result(parsed):
                    return parsed

                logger.warning(f"파싱 결과 검증 실패 for {name}. Fallback to Regex.")
            except json.JSONDecodeError as e:
                logger.warning(f"JSON 파싱 실패 for {name}: {e}. Fallback to Regex.")

        # Level 4 Fallback: Level 2에서 이미 계산한 regex_result 재사용
        return regex_result

    def _extract_json_from_response(self, text: str) -> str:
        """LLM 응답에서 JSON 부분만 추출 (마크다운 코드블록 제거)."""
        text = text.strip()

        # ```json ... ``` 형태
        if text.startswith("```json"):
            text = text[7:]
        elif text.startswith("```"):
            text = text[3:]

        if text.endswith("```"):
            text = text[:-3]

        return text.strip()
    
    def _validate_parsed_result(self, result: Dict[str, Any]) -> bool:
        """
        Validate a parsed room dictionary against the expected schema and realistic numeric ranges.
        
        Parameters:
            result (Dict[str, Any]): Parsed room data to validate.
        
        Checks performed:
            - Presence of required field `clean_name`.
            - `max_capacity`, if present, must be a number between 1 and 50 inclusive.
            - `recommend_capacity`, if present, must be a number between 1 and 50 inclusive.
            - `extra_charge`, if present, must be a number between 0 and 50,000 inclusive.
            - `day_type`, if present, must be either "weekday" or "weekend".
            - `recommend_capacity_range`, if present, must be a list of two numbers `[min, max]` with 1 <= min <= max <= 50.
        
        Returns:
            bool: `True` if all checks pass, `False` otherwise.
        """
        # 1. 필수 필드 존재 확인
        if "clean_name" not in result:
            return False
        
        # 2. 최대 수용 인원 범위 검증 (합주실 현실적 범위: 1~50명)
        max_cap = result.get("max_capacity")
        if max_cap is not None:
            if not isinstance(max_cap, (int, float)) or max_cap < 1 or max_cap > 50:
                return False
        
        # 3. 권장 인원 범위 검증
        rec_cap = result.get("recommend_capacity")
        if rec_cap is not None:
            if not isinstance(rec_cap, (int, float)) or rec_cap < 1 or rec_cap > 50:
                return False
        
        # 4. 추가 요금 범위 검증 (0~50,000원)
        extra = result.get("extra_charge")
        if extra is not None:
            if not isinstance(extra, (int, float)) or extra < 0 or extra > 50000:
                return False
        
        # 5. day_type 값 검증
        day_type = result.get("day_type")
        if day_type is not None and day_type not in ["weekday", "weekend"]:
            return False
        
        # 6. [v2.0.0] recommend_capacity_range 검증
        # Rationale: 배열이면 반드시 [min, max] 2원소이고, min <= max여야 함
        rec_range = result.get("recommend_capacity_range")
        if rec_range is not None:
            if not isinstance(rec_range, list) or len(rec_range) != 2:
                return False
            if not all(isinstance(v, (int, float)) for v in rec_range):
                return False
            if rec_range[0] < 1 or rec_range[1] > 50 or rec_range[0] > rec_range[1]:
                return False
        
        return True

    def _parse_with_regex(self, name: str, desc: str) -> Dict[str, Any]:
        """
        정규표현식을 사용해 룸 이름(name)과 설명(desc)에서 구조화된 룸 정보를 추출하는 Fallback 파서입니다.
        
        설명:
        - LLM 파싱 실패 시 사용하며, 용량 정보는 설명(desc)을 우선적으로 검색하고 없으면 이름(name)에서 추출합니다.
        - 추출된 용량 정보로 recommend_capacity_range 필드를 구성하며, 범위가 있으면 `[min, max]`, 단일값이면 `[n, n]`으로 변환합니다.
        
        Returns:
            result (dict): 다음 키를 포함하는 딕셔너리
                - clean_name (str): 용량/주말표시 등 메타 정보를 제거한 정제된 이름
                - day_type (str|None): "weekday", "weekend" 또는 None
                - max_capacity (int|None): 추출된 최대 수용 인원
                - recommend_capacity (int|None): 권장 인원(단일값)
                - recommend_capacity_range (list|None): [min, max] 형태의 권장 인원 범위
                - base_capacity (int|None): "기본 X인"으로 추출된 기본 수용 인원
                - extra_charge (int|None): 추가 요금(원 단위)
                - requires_call_on_same_day (bool): 당일 예약 시 전화/문의 필요 여부
        """
        desc = desc or ""

        # 1. clean_name & day_type
        clean_name = name
        day_type = None

        if "[평일]" in name or "(평일)" in name:
            day_type = "weekday"
            clean_name = re.sub(r'\[평일\]|\(평일\)', '', clean_name).strip()
        elif "[주말]" in name or "(주말)" in name or "주말/공휴일" in name:
            day_type = "weekend"
            clean_name = re.sub(r'\[주말[^\]]*\]|\(주말[^)]*\)|\[주말/공휴일\]', '', clean_name).strip()

        # Clean capacity info from name (e.g., "(정원 13명, 최대 18명)", "(-15명)")
        clean_name = re.sub(r'\s*\(?\s*정원\s*\d+\s*(?:인|명)\s*,?\s*(?:최대\s*\d+\s*(?:인|명))?\s*\)?', '', clean_name).strip()
        clean_name = re.sub(r'\s*\(?\s*최대\s*\d+\s*(?:인|명)\s*\)?', '', clean_name).strip()
        clean_name = re.sub(r'\s*\(\s*-\s*\d+\s*(?:인|명)\s*\)', '', clean_name).strip()

        # 2. Capacity extraction - prioritize desc, fallback to name
        max_cap = None
        rec_cap = None

        # Try extracting from desc first
        max_cap, rec_cap, parsed_range = self._extract_capacity_from_text(desc)

        # If not found in desc, try name field
        if not max_cap and not rec_cap:
            max_cap_from_name, rec_cap_from_name, range_from_name = self._extract_capacity_from_text(name)
            max_cap = max_cap_from_name
            rec_cap = rec_cap_from_name
            if not parsed_range:
                parsed_range = range_from_name

        # Set default recommend_capacity based on max_capacity if not found
        if max_cap and not rec_cap:
            rec_cap = max_cap // 2 if max_cap > 4 else max_cap

        # 3. Base Capacity & Extra Charge
        base_cap = None
        extra_charge = None

        # "기본 4인"
        base_match = re.search(r'기본\s*(\d+)', desc)
        if base_match:
            base_cap = int(base_match.group(1))

        # "1인 추가시 3000원", "인당 3000원"
        charge_match = re.search(r'(?:1인|인당)\s*(?:추가)?.*?(\d+(?:,\d+)?)\s*원', desc)
        if charge_match:
            extra_charge = int(charge_match.group(1).replace(',', ''))

        # 4. Same day call
        requires_call = "당일" in desc and ("전화" in desc or "문의" in desc)

        # [v2.0.0] recommend_capacity_range 구성
        # Rationale: 범위 정보가 있으면 [min, max]로, 단일 값이면 [n, n]으로 변환
        rec_range = parsed_range  # 범위 추출 결과가 있으면 그대로 사용
        if not rec_range and rec_cap:
            rec_range = [rec_cap, rec_cap]  # 단일값은 [n, n]으로 디폴트

        return {
            "clean_name": clean_name,
            "day_type": day_type,
            "max_capacity": max_cap,
            "recommend_capacity": rec_cap,
            "recommend_capacity_range": rec_range,
            "base_capacity": base_cap,
            "extra_charge": extra_charge,
            "requires_call_on_same_day": requires_call
        }

    def _extract_capacity_from_text(self, text: str) -> tuple[Optional[int], Optional[int], Optional[list]]:
        """텍스트에서 max_capacity와 recommend_capacity, 범위를 추출합니다.

        Args:
            text: 검색할 텍스트 (name 또는 desc)

        Returns:
            (max_capacity, recommend_capacity, capacity_range) 튜플
            capacity_range는 [min, max] 형태이며, 범위 정보가 없으면 None
        """
        max_cap = None
        rec_cap = None
        capacity_range = None

        # Pattern 1: "(정원 N명, 최대 M명)" - name field에 흔함
        capacity_paren_match = re.search(r'\(\s*정원\s*(\d+)\s*(?:인|명)\s*,\s*최대\s*(\d+)\s*(?:인|명)\s*\)', text)
        if capacity_paren_match:
            rec_cap = int(capacity_paren_match.group(1))
            max_cap = int(capacity_paren_match.group(2))
            return max_cap, rec_cap, None

        # Pattern 2: "정원 N명" alone (recommended capacity)
        recommend_match = re.search(r'정원\s*(\d+)\s*(?:인|명)', text)
        if recommend_match:
            rec_cap = int(recommend_match.group(1))

        # Pattern 3: "최대 N인/명" or "Max N명"
        max_match = re.search(r'(?:최대|max|MAX)\s*(\d+)', text, re.IGNORECASE)
        if max_match:
            max_cap = int(max_match.group(1))

        # Pattern 4: "N인까지", "N명까지", "N인 까지", "N인이하"
        if not max_cap:
            until_match = re.search(r'(\d+)\s*(?:인|명)\s*(?:까지|이하|수용)', text)
            if until_match:
                max_cap = int(until_match.group(1))

        # Pattern 5: "N인이 합주 가능", "N인 합주 가능", "N인이 이용 가능"
        if not max_cap:
            usage_match = re.search(r'(\d+)\s*(?:인|명)(?:이|이서)?\s*(?:합주|이용|수용)?\s*가능', text)
            if usage_match:
                max_cap = int(usage_match.group(1))

        # Pattern 7: "(-N명)", "(-N인)" - 이름에 괄호로 최대인원 표기 (e.g., "R룸 (-15명)")
        if not max_cap:
            paren_max_match = re.search(r'\(\s*-\s*(\d+)\s*(?:인|명)\s*\)', text)
            if paren_max_match:
                max_cap = int(paren_max_match.group(1))

        # Pattern 6: "N~M인", "N~M명", "권장 인원 N명 M명" (range with ~, -, or space)
        # NOTE: 인/명 접미사 필수 - 장비 모델명 오파싱 방지 (e.g., "OB1-500")
        range_match = re.search(r'(\d+)\s*[~\-]\s*(\d+)\s*(?:인|명)', text)
        if range_match:
            min_r = int(range_match.group(1))
            max_r = int(range_match.group(2))
            rec_cap = (min_r + max_r) // 2
            # [v2.0.0] 범위 원본 저장
            capacity_range = [min_r, max_r]
            if not max_cap:
                max_cap = max_r
        elif not rec_cap and not range_match:
            # "권장 인원 10명 12명" - space separated range
            space_range_match = re.search(r'권장\s*인원\s*(\d+)\s*(?:인|명)\s*(\d+)\s*(?:인|명)', text)
            if space_range_match:
                min_r = int(space_range_match.group(1))
                max_r = int(space_range_match.group(2))
                rec_cap = (min_r + max_r) // 2
                capacity_range = [min_r, max_r]
                if not max_cap:
                    max_cap = max_r

        return max_cap, rec_cap, capacity_range

    async def parse_room_desc_batch(self, items: List[Dict]) -> Dict[str, Dict]:
        """
        Parse multiple room entries into structured room metadata, using the LLM and falling back to regex extraction when parsing or validation fails.
        
        Parameters:
            items (List[Dict]): List of room items in the form [{"id": "<id>", "name": "<name>", "desc": "<description>"}]. Each item must contain an "id" and "name"; "desc" may be omitted or None.
        
        Returns:
            Dict[str, Dict]: Mapping from each input `id` to its parsed room data dictionary. Returns an empty dict when `items` is empty. If LLM parsing fails or an individual result fails validation, that item's value is produced by the regex fallback parser.
        """
        if not items:
            return {}
        
        # 프롬프트 구성
        rooms_text_parts = []
        for item in items:
            rooms_text_parts.append(
                f"ID: {item['id']}\nName: {item['name']}\nDesc: {item.get('desc') or ''}\n---"
            )
        
        prompt = BATCH_PARSE_PROMPT.format(rooms_text="\n".join(rooms_text_parts))
        
        # Ollama LLM 파싱 시도
        response = await self.ollama_client.generate(prompt, max_tokens=1024)
        
        if response:
            try:
                text = self._extract_json_from_response(response)
                parsed_results = json.loads(text)
                
                # 각 아이템별로 검증, 실패 시 Regex Fallback
                final_results = {}
                for item in items:
                    rid = item["id"]
                    data = parsed_results.get(rid)
                    if data and self._validate_parsed_result(data):
                        final_results[rid] = data
                    else:
                        logger.warning(f"배치 파싱 검증 실패: {rid}, Regex fallback 사용.")
                        final_results[rid] = self._parse_with_regex(item["name"], item["desc"])
                        
                return final_results
                
            except json.JSONDecodeError as e:
                logger.warning(f"배치 JSON 파싱 실패: {e}. 전체 Regex fallback.")
        
        # Fallback: 모든 아이템을 Regex로 파싱
        return {
            item["id"]: self._parse_with_regex(item["name"], item["desc"]) 
            for item in items
        }