import argparse
import asyncio
import json
import os
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# Add project root to path for module discovery
sys.path.append(os.getcwd())

from app.core.ollama_client import OllamaClient
from app.crawler.naver_map_crawler import NaverMapCrawler
from app.crawler.naver_room_fetcher import NaverRoomFetcher
from app.services.room_parser_service import RoomParserService


def _to_obj(value: Any) -> Any:
    if isinstance(value, (dict, list)):
        return value
    if isinstance(value, str):
        try:
            return json.loads(value)
        except Exception:
            return value
    return value


def _iter_key_values(obj: Any):
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield str(k), v
            yield from _iter_key_values(v)
    elif isinstance(obj, list):
        for item in obj:
            yield from _iter_key_values(item)


def _to_int(value: Any) -> Optional[int]:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        digits = "".join(ch for ch in value if ch.isdigit())
        if digits:
            try:
                return int(digits)
            except Exception:
                return None
    return None


def _find_first_int_by_key(obj: Any, key_tokens: List[str]) -> Optional[int]:
    for key, value in _iter_key_values(obj):
        lk = key.lower()
        if all(token in lk for token in key_tokens):
            candidate = _to_int(value)
            if candidate is not None:
                return candidate
    return None


def _infer_can_reserve_one_hour(min_booking_time: Any, unit_code: Any) -> Optional[bool]:
    min_value = _to_int(min_booking_time)
    if min_value is None:
        return None

    unit = str(unit_code or "").upper()
    # If the unit is minute based, 60 minutes or less means one-hour reservation is possible.
    if "MIN" in unit:
        return min_value <= 60
    # Default assumes hour based.
    return min_value <= 1


def _extract_capacity_from_text(name: str, desc: str) -> Tuple[Optional[int], Optional[int], Dict[str, str]]:
    text = f"{name or ''} {desc or ''}"
    sources: Dict[str, str] = {}

    # High-confidence pattern: "(정원 N명, 최대 M명)"
    pair = None
    import re

    pair = re.search(r"정원\s*(\d+)\s*명[^\\d]*최대\s*(\d+)\s*명", text)
    if pair:
        recommend = _to_int(pair.group(1))
        max_cap = _to_int(pair.group(2))
        if recommend is not None:
            sources["recommend_capacity"] = "text:정원 N명"
        if max_cap is not None:
            sources["max_capacity"] = "text:최대 M명"
        return max_cap, recommend, sources

    recommend = None
    max_cap = None
    rec_match = re.search(r"정원\s*(\d+)\s*명", text)
    if rec_match:
        recommend = _to_int(rec_match.group(1))
        sources["recommend_capacity"] = "text:정원 N명"

    max_match = re.search(r"최대\s*(\d+)\s*명", text)
    if max_match:
        max_cap = _to_int(max_match.group(1))
        sources["max_capacity"] = "text:최대 N명"

    return max_cap, recommend, sources


def _extract_extra_charge(room: Dict[str, Any], desc: str) -> Tuple[Optional[int], Optional[str]]:
    booking_json = _to_obj(room.get("bookingCountSettingJson"))
    extra_fee_json = _to_obj(room.get("extraFeeSettingJson"))

    # booking_json is kept for possible future schema extension.
    _ = booking_json
    if isinstance(extra_fee_json, (dict, list)):
        extra_from_json = (
            _find_first_int_by_key(extra_fee_json, ["extra", "fee"])
            or _find_first_int_by_key(extra_fee_json, ["extra", "charge"])
            or _find_first_int_by_key(extra_fee_json, ["additional", "fee"])
            or _find_first_int_by_key(extra_fee_json, ["surcharge"])
            or _find_first_int_by_key(extra_fee_json, ["amount"])
        )
        if extra_from_json is not None:
            return extra_from_json, "extraFeeSettingJson"

    import re

    text_charge = re.search(r"(?:1인당|인당)\s*(\d[\d,]*)\s*원", desc or "")
    if text_charge:
        charge = _to_int(text_charge.group(1))
        if charge is not None:
            return charge, "text:인당 N원"

    return None, None


def _expected_from_structured(room: Dict[str, Any]) -> Tuple[Dict[str, Any], Dict[str, str]]:
    max_cap, rec_cap, text_sources = _extract_capacity_from_text(
        room.get("name") or "",
        room.get("desc") or "",
    )
    extra_charge, extra_source = _extract_extra_charge(room, room.get("desc") or "")

    expected: Dict[str, Any] = {
        "max_capacity": max_cap,
        "recommend_capacity": rec_cap,
        "extra_charge": extra_charge,
        "can_reserve_one_hour": _infer_can_reserve_one_hour(
            room.get("minBookingTime"),
            room.get("bookingTimeUnitCode"),
        ),
    }
    sources: Dict[str, str] = {
        "can_reserve_one_hour": "minBookingTime + bookingTimeUnitCode",
    }
    sources.update(text_sources)
    if extra_source:
        sources["extra_charge"] = extra_source

    return expected, sources


def _match(expected: Any, actual: Any) -> Optional[bool]:
    if expected is None:
        return None
    if actual is None:
        return False
    if isinstance(expected, bool):
        return bool(actual) == expected
    return _to_int(actual) == _to_int(expected)


def _summarize_matches(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    fields = ["max_capacity", "recommend_capacity", "extra_charge", "can_reserve_one_hour"]
    out: Dict[str, Any] = {}

    for field in fields:
        eligible = 0
        with_match = 0
        without_match = 0
        for row in rows:
            m_with = row["match"]["with"].get(field)
            m_without = row["match"]["without"].get(field)
            if m_with is None:
                continue
            eligible += 1
            if m_with:
                with_match += 1
            if m_without:
                without_match += 1
        out[field] = {
            "eligible": eligible,
            "with_context_match": with_match,
            "without_context_match": without_match,
            "with_context_rate": round(with_match / eligible, 3) if eligible else None,
            "without_context_rate": round(without_match / eligible, 3) if eligible else None,
            "delta": with_match - without_match,
        }
    return out


async def _resolve_business_ids(query: str, limit: int) -> List[str]:
    crawler = NaverMapCrawler()
    items = await crawler.search_rehearsal_rooms(query)
    business_ids = []
    for item in items:
        bid = item.get("id")
        if bid:
            business_ids.append(str(bid))
        if len(business_ids) >= limit:
            break
    return business_ids


async def run(args: argparse.Namespace) -> Dict[str, Any]:
    business_ids = list(dict.fromkeys(args.business_ids))
    if args.query:
        from_query = await _resolve_business_ids(args.query, args.limit)
        business_ids.extend([bid for bid in from_query if bid not in business_ids])
    if args.limit and len(business_ids) > args.limit:
        business_ids = business_ids[: args.limit]

    if not business_ids:
        raise ValueError("No target businesses. Use --business-id or --query.")

    fetcher = NaverRoomFetcher()
    parser_service = RoomParserService(ollama_client=OllamaClient(model=args.model))

    room_rows: List[Dict[str, Any]] = []
    crawl_presence = defaultdict(int)
    total_rooms = 0

    for business_id in business_ids:
        data = await fetcher.fetch_full_info(business_id)
        if not data:
            continue
        business = data.get("business") or {}
        rooms = data.get("rooms") or []
        business_desc = business.get("desc") or ""

        items_with = []
        items_without = []
        for room in rooms:
            total_rooms += 1
            if room.get("desc"):
                crawl_presence["room_desc"] += 1
            if business_desc:
                crawl_presence["business_desc"] += 1
            for key in [
                "maxBookingCount",
                "minBookingCount",
                "minBookingTime",
                "bookingTimeUnitCode",
                "bookingCountSettingJson",
                "extraFeeSettingJson",
            ]:
                if room.get(key) is not None:
                    crawl_presence[key] += 1

            items_with.append(
                {
                    "id": room["bizItemId"],
                    "name": room["name"],
                    "desc": room.get("desc") or "",
                    "business_desc": business_desc,
                }
            )
            items_without.append(
                {
                    "id": room["bizItemId"],
                    "name": room["name"],
                    "desc": room.get("desc") or "",
                    "business_desc": "",
                }
            )

        parsed_with = await parser_service.parse_room_desc_batch(items_with) if items_with else {}
        parsed_without = (
            await parser_service.parse_room_desc_batch(items_without) if items_without else {}
        )

        rooms_by_id = {str(r.get("bizItemId")): r for r in rooms}
        for rid, room in rooms_by_id.items():
            expected, sources = _expected_from_structured(room)
            with_row = parsed_with.get(rid, {})
            without_row = parsed_without.get(rid, {})

            room_rows.append(
                {
                    "business_id": business_id,
                    "biz_item_id": rid,
                    "room_name": room.get("name"),
                    "expected": expected,
                    "expected_sources": sources,
                    "parsed_with_context": {
                        "max_capacity": with_row.get("max_capacity"),
                        "recommend_capacity": with_row.get("recommend_capacity"),
                        "base_capacity": with_row.get("base_capacity"),
                        "extra_charge": with_row.get("extra_charge"),
                        "can_reserve_one_hour": with_row.get("can_reserve_one_hour"),
                    },
                    "parsed_without_context": {
                        "max_capacity": without_row.get("max_capacity"),
                        "recommend_capacity": without_row.get("recommend_capacity"),
                        "base_capacity": without_row.get("base_capacity"),
                        "extra_charge": without_row.get("extra_charge"),
                        "can_reserve_one_hour": without_row.get("can_reserve_one_hour"),
                    },
                    "match": {
                        "with": {
                            k: _match(expected.get(k), with_row.get(k))
                            for k in expected.keys()
                        },
                        "without": {
                            k: _match(expected.get(k), without_row.get(k))
                            for k in expected.keys()
                        },
                    },
                }
            )

    summary = _summarize_matches(room_rows)

    llm_split = {
        "llm_not_required_or_primary_structured": [
            "price_per_hour (minMaxPrice)",
            "minBookingCount/maxBookingCount",
            "minBookingTime/maxBookingTime",
            "isOnsitePayment",
            "bookingCountSettingJson/extraFeeSettingJson (if schema is stable)",
        ],
        "llm_required_or_text_dominant": [
            "recommend_capacity",
            "day_type (weekday/weekend tags)",
            "requires_call_on_same_day",
            "implicit rules written only in desc",
        ],
        "hybrid_recommended": [
            "max_capacity (structured maxBookingCount + desc fallback)",
            "base_capacity and extra_charge (JSON first, desc second)",
            "can_reserve_one_hour (minBookingTime first, desc fallback)",
        ],
    }

    return {
        "evaluated_at": datetime.now().isoformat(),
        "model": args.model,
        "target_business_ids": business_ids,
        "total_rooms": total_rooms,
        "crawl_field_presence": {
            "room_desc_ratio": round(crawl_presence["room_desc"] / total_rooms, 3)
            if total_rooms
            else None,
            "business_desc_ratio": round(crawl_presence["business_desc"] / total_rooms, 3)
            if total_rooms
            else None,
            "maxBookingCount_ratio": round(crawl_presence["maxBookingCount"] / total_rooms, 3)
            if total_rooms
            else None,
            "minBookingCount_ratio": round(crawl_presence["minBookingCount"] / total_rooms, 3)
            if total_rooms
            else None,
            "minBookingTime_ratio": round(crawl_presence["minBookingTime"] / total_rooms, 3)
            if total_rooms
            else None,
            "bookingCountSettingJson_ratio": round(
                crawl_presence["bookingCountSettingJson"] / total_rooms, 3
            )
            if total_rooms
            else None,
            "extraFeeSettingJson_ratio": round(
                crawl_presence["extraFeeSettingJson"] / total_rooms, 3
            )
            if total_rooms
            else None,
        },
        "parser_match_summary": summary,
        "llm_usage_classification": llm_split,
        "rooms": room_rows,
    }


def _default_output_path() -> Path:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    return Path("scripts") / "reports" / f"parser_eval_{ts}.json"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Evaluate parser results against crawled structured fields."
    )
    parser.add_argument("--business-id", dest="business_ids", action="append", default=[])
    parser.add_argument("--query", default="")
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--model", default=os.getenv("OLLAMA_MODEL", "llama3.2:3b"))
    parser.add_argument("--output", default="")
    return parser.parse_args()


async def main() -> int:
    args = parse_args()
    report = await run(args)

    out_path = Path(args.output) if args.output else _default_output_path()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"saved_report={out_path}")
    print(f"total_rooms={report['total_rooms']}")
    print("parser_match_summary=" + json.dumps(report["parser_match_summary"], ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
