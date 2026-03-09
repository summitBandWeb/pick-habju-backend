from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.core.supabase_client import supabase


KOREA_LAT_MIN = 33.0
KOREA_LAT_MAX = 39.5
KOREA_LNG_MIN = 124.0
KOREA_LNG_MAX = 132.0


def is_blank(value: Any) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())


def pct(numerator: int, denominator: int) -> float:
    if denominator == 0:
        return 0.0
    return round((numerator / denominator) * 100, 2)


def normalize_phone(raw: Any) -> str:
    if raw is None:
        return ""
    text = str(raw).strip()
    if not text:
        return ""
    compact = re.sub(r"[^\d+]", "", text)
    if compact.startswith("+82"):
        compact = "0" + compact[3:]
    elif compact.startswith("82"):
        compact = "0" + compact[2:]
    return re.sub(r"\D", "", compact)


def is_valid_phone(raw: Any) -> bool:
    normalized = normalize_phone(raw)
    if not normalized:
        return False
    if not normalized.startswith("0"):
        return False
    # Korean domestic numbers are typically 9~11 digits.
    return normalized.isdigit() and 9 <= len(normalized) <= 11


def _to_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def coordinate_quality(lat: Any, lng: Any) -> str:
    lat_f = _to_float(lat)
    lng_f = _to_float(lng)
    if lat_f is None or lng_f is None:
        return "missing_or_non_numeric"

    lat_ok = KOREA_LAT_MIN <= lat_f <= KOREA_LAT_MAX
    lng_ok = KOREA_LNG_MIN <= lng_f <= KOREA_LNG_MAX
    if lat_ok and lng_ok:
        return "ok"

    swapped_lat_ok = KOREA_LAT_MIN <= lng_f <= KOREA_LAT_MAX
    swapped_lng_ok = KOREA_LNG_MIN <= lat_f <= KOREA_LNG_MAX
    if swapped_lat_ok and swapped_lng_ok:
        return "swapped"

    return "out_of_korea_range"


def fetch_all_by_business_ids(
    table: str,
    columns: str,
    business_ids: list[str],
    page_size: int = 1000,
) -> list[dict[str, Any]]:
    if not business_ids:
        return []
    rows: list[dict[str, Any]] = []
    start = 0
    while True:
        end = start + page_size - 1
        result = (
            supabase.table(table)
            .select(columns)
            .in_("business_id", business_ids)
            .range(start, end)
            .execute()
        )
        chunk = result.data or []
        rows.extend(chunk)
        if len(chunk) < page_size:
            break
        start += page_size
    return rows


def parse_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def parse_money(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def make_report(allowlist_ids: list[str]) -> dict[str, Any]:
    branch_rows = fetch_all_by_business_ids(
        table="branch",
        columns="business_id,name,display_name,phone_number,lat,lng,standby_days",
        business_ids=allowlist_ids,
    )
    room_rows = fetch_all_by_business_ids(
        table="room",
        columns=(
            "business_id,biz_item_id,name,max_capacity,recommend_capacity,"
            "recommend_capacity_range,price_per_hour,price_config,base_capacity,extra_charge"
        ),
        business_ids=allowlist_ids,
    )

    branch_by_id = {row["business_id"]: row for row in branch_rows}
    rooms_by_business: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for room in room_rows:
        rooms_by_business[room["business_id"]].append(room)

    missing_branch_ids: list[str] = []
    missing_branch_name_ids: list[str] = []
    missing_phone_ids: list[str] = []
    invalid_phone_items: list[dict[str, Any]] = []
    missing_display_name_ids: list[str] = []
    missing_coordinate_ids: list[str] = []
    swapped_coordinate_items: list[dict[str, Any]] = []
    out_of_range_coordinate_items: list[dict[str, Any]] = []
    branch_without_rooms_ids: list[str] = []

    for business_id in allowlist_ids:
        branch = branch_by_id.get(business_id)
        if not branch:
            missing_branch_ids.append(business_id)
            continue

        if is_blank(branch.get("name")):
            missing_branch_name_ids.append(business_id)

        if is_blank(branch.get("display_name")):
            missing_display_name_ids.append(business_id)

        phone = branch.get("phone_number")
        if is_blank(phone):
            missing_phone_ids.append(business_id)
        elif not is_valid_phone(phone):
            invalid_phone_items.append({"business_id": business_id, "phone_number": phone})

        coord_status = coordinate_quality(branch.get("lat"), branch.get("lng"))
        if coord_status == "missing_or_non_numeric":
            missing_coordinate_ids.append(business_id)
        elif coord_status == "swapped":
            swapped_coordinate_items.append(
                {
                    "business_id": business_id,
                    "lat": branch.get("lat"),
                    "lng": branch.get("lng"),
                }
            )
        elif coord_status == "out_of_korea_range":
            out_of_range_coordinate_items.append(
                {
                    "business_id": business_id,
                    "lat": branch.get("lat"),
                    "lng": branch.get("lng"),
                }
            )

        if not rooms_by_business.get(business_id):
            branch_without_rooms_ids.append(business_id)

    duplicate_room_key_items: list[dict[str, str]] = []
    room_missing_name_items: list[dict[str, str]] = []
    room_invalid_capacity_items: list[dict[str, Any]] = []
    room_price_missing_items: list[dict[str, str]] = []
    room_negative_price_items: list[dict[str, Any]] = []
    room_invalid_base_capacity_items: list[dict[str, Any]] = []

    seen_room_keys: set[tuple[str, str]] = set()
    for room in room_rows:
        business_id = room["business_id"]
        biz_item_id = room["biz_item_id"]
        room_key = (business_id, biz_item_id)
        if room_key in seen_room_keys:
            duplicate_room_key_items.append(
                {"business_id": business_id, "biz_item_id": biz_item_id}
            )
        seen_room_keys.add(room_key)

        if is_blank(room.get("name")):
            room_missing_name_items.append(
                {"business_id": business_id, "biz_item_id": biz_item_id}
            )

        max_capacity = parse_int(room.get("max_capacity"))
        recommend_capacity = parse_int(room.get("recommend_capacity"))
        base_capacity = parse_int(room.get("base_capacity"))

        invalid_capacity_reason: list[str] = []
        if max_capacity is None or max_capacity < 1:
            invalid_capacity_reason.append("max_capacity_invalid")
        if recommend_capacity is not None:
            if recommend_capacity < 1:
                invalid_capacity_reason.append("recommend_capacity_invalid")
            if max_capacity is not None and recommend_capacity > max_capacity:
                invalid_capacity_reason.append("recommend_capacity_exceeds_max")
        if invalid_capacity_reason:
            room_invalid_capacity_items.append(
                {
                    "business_id": business_id,
                    "biz_item_id": biz_item_id,
                    "max_capacity": room.get("max_capacity"),
                    "recommend_capacity": room.get("recommend_capacity"),
                    "reason": invalid_capacity_reason,
                }
            )

        price_per_hour = parse_money(room.get("price_per_hour"))
        extra_charge = parse_money(room.get("extra_charge"))
        price_config = room.get("price_config")
        if price_per_hour is None and price_config is None:
            room_price_missing_items.append(
                {"business_id": business_id, "biz_item_id": biz_item_id}
            )
        if price_per_hour is not None and price_per_hour < 0:
            room_negative_price_items.append(
                {
                    "business_id": business_id,
                    "biz_item_id": biz_item_id,
                    "field": "price_per_hour",
                    "value": room.get("price_per_hour"),
                }
            )
        if extra_charge is not None and extra_charge < 0:
            room_negative_price_items.append(
                {
                    "business_id": business_id,
                    "biz_item_id": biz_item_id,
                    "field": "extra_charge",
                    "value": room.get("extra_charge"),
                }
            )

        if base_capacity is not None:
            if base_capacity < 1:
                room_invalid_base_capacity_items.append(
                    {
                        "business_id": business_id,
                        "biz_item_id": biz_item_id,
                        "base_capacity": room.get("base_capacity"),
                        "max_capacity": room.get("max_capacity"),
                        "reason": "base_capacity_less_than_1",
                    }
                )
            elif max_capacity is not None and base_capacity > max_capacity:
                room_invalid_base_capacity_items.append(
                    {
                        "business_id": business_id,
                        "biz_item_id": biz_item_id,
                        "base_capacity": room.get("base_capacity"),
                        "max_capacity": room.get("max_capacity"),
                        "reason": "base_capacity_exceeds_max_capacity",
                    }
                )

    matched_branch_count = len(branch_rows)
    valid_phone_count = (
        matched_branch_count - len(missing_phone_ids) - len(invalid_phone_items)
    )
    valid_coordinate_count = (
        matched_branch_count
        - len(missing_coordinate_ids)
        - len(swapped_coordinate_items)
        - len(out_of_range_coordinate_items)
    )
    branches_with_rooms_count = matched_branch_count - len(branch_without_rooms_ids)

    summary = {
        "allowlist_count": len(allowlist_ids),
        "branch_count_in_db": matched_branch_count,
        "room_count_in_db": len(room_rows),
        "branch_coverage_pct": pct(matched_branch_count, len(allowlist_ids)),
        "branch_name_completeness_pct": pct(
            matched_branch_count - len(missing_branch_name_ids), matched_branch_count
        ),
        "display_name_completeness_pct": pct(
            matched_branch_count - len(missing_display_name_ids), matched_branch_count
        ),
        "phone_valid_pct": pct(valid_phone_count, matched_branch_count),
        "coordinate_valid_pct": pct(valid_coordinate_count, matched_branch_count),
        "branches_with_rooms_pct": pct(branches_with_rooms_count, matched_branch_count),
        "room_name_completeness_pct": pct(
            len(room_rows) - len(room_missing_name_items), len(room_rows)
        ),
        "room_capacity_valid_pct": pct(
            len(room_rows) - len(room_invalid_capacity_items), len(room_rows)
        ),
        "room_price_present_pct": pct(
            len(room_rows) - len(room_price_missing_items), len(room_rows)
        ),
        "room_negative_price_issue_count": len(room_negative_price_items),
        "room_invalid_base_capacity_count": len(room_invalid_base_capacity_items),
        "duplicate_room_key_count": len(duplicate_room_key_items),
    }

    return {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "scope": "priority_area_allowlist",
        "summary": summary,
        "details": {
            "missing_branch_ids": sorted(missing_branch_ids),
            "missing_branch_name_ids": sorted(missing_branch_name_ids),
            "missing_display_name_ids": sorted(missing_display_name_ids),
            "missing_phone_ids": sorted(missing_phone_ids),
            "invalid_phone_items": sorted(
                invalid_phone_items, key=lambda x: str(x["business_id"])
            ),
            "missing_coordinate_ids": sorted(missing_coordinate_ids),
            "swapped_coordinate_items": sorted(
                swapped_coordinate_items, key=lambda x: str(x["business_id"])
            ),
            "out_of_range_coordinate_items": sorted(
                out_of_range_coordinate_items, key=lambda x: str(x["business_id"])
            ),
            "branch_without_rooms_ids": sorted(branch_without_rooms_ids),
            "duplicate_room_key_items": sorted(
                duplicate_room_key_items,
                key=lambda x: (str(x["business_id"]), str(x["biz_item_id"])),
            ),
            "room_missing_name_items": sorted(
                room_missing_name_items,
                key=lambda x: (str(x["business_id"]), str(x["biz_item_id"])),
            ),
            "room_invalid_capacity_items": sorted(
                room_invalid_capacity_items,
                key=lambda x: (str(x["business_id"]), str(x["biz_item_id"])),
            ),
            "room_price_missing_items": sorted(
                room_price_missing_items,
                key=lambda x: (str(x["business_id"]), str(x["biz_item_id"])),
            ),
            "room_negative_price_items": sorted(
                room_negative_price_items,
                key=lambda x: (str(x["business_id"]), str(x["biz_item_id"])),
            ),
            "room_invalid_base_capacity_items": sorted(
                room_invalid_base_capacity_items,
                key=lambda x: (str(x["business_id"]), str(x["biz_item_id"])),
            ),
        },
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate DB data quality for allowlist businesses."
    )
    parser.add_argument(
        "--output",
        type=str,
        default="",
        help="Optional output JSON path. Defaults to logs/allowlist_quality_report_YYYY-MM-DD.json",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    allowlist_ids = [
        row["business_id"]
        for row in supabase.table("branch").select("business_id").execute().data
    ]
    report = make_report(allowlist_ids)

    if args.output:
        output_path = Path(args.output)
    else:
        date_tag = datetime.now().strftime("%Y-%m-%d")
        output_path = Path("logs") / f"allowlist_quality_report_{date_tag}.json"

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    summary = report["summary"]
    print(f"[allowlist quality] report saved: {output_path}")
    print(f"- allowlist_count: {summary['allowlist_count']}")
    print(f"- branch_count_in_db: {summary['branch_count_in_db']}")
    print(f"- room_count_in_db: {summary['room_count_in_db']}")
    print(f"- branch_coverage_pct: {summary['branch_coverage_pct']}")
    print(f"- phone_valid_pct: {summary['phone_valid_pct']}")
    print(f"- coordinate_valid_pct: {summary['coordinate_valid_pct']}")
    print(f"- branches_with_rooms_pct: {summary['branches_with_rooms_pct']}")
    print(f"- room_name_completeness_pct: {summary['room_name_completeness_pct']}")
    print(f"- room_capacity_valid_pct: {summary['room_capacity_valid_pct']}")
    print(f"- room_price_present_pct: {summary['room_price_present_pct']}")


if __name__ == "__main__":
    main()
