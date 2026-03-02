import argparse
import asyncio
import json
import logging
import os
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple

from dotenv import load_dotenv

# Add project root to path for module discovery
sys.path.append(os.getcwd())

from app.core.supabase_client import get_supabase_client
from app.services.room_collection_service import RoomCollectionService


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)


def count_flagged_rooms(flag_value: int) -> int:
    """Count rows where max_capacity is the manual-review flag value."""
    supabase = get_supabase_client()
    resp = (
        supabase.table("room")
        .select("*", count="exact", head=True)
        .eq("max_capacity", flag_value)
        .execute()
    )
    return int(resp.count or 0)


def fetch_flagged_rooms(flag_value: int, page_size: int = 500) -> List[Dict]:
    """Fetch all rows where max_capacity is flag_value with pagination."""
    supabase = get_supabase_client()
    all_rows: List[Dict] = []
    offset = 0

    while True:
        resp = (
            supabase.table("room")
            .select("business_id,biz_item_id,name,max_capacity,recommend_capacity")
            .eq("max_capacity", flag_value)
            .range(offset, offset + page_size - 1)
            .execute()
        )
        rows = resp.data or []
        if not rows:
            break

        all_rows.extend(rows)
        if len(rows) < page_size:
            break
        offset += page_size

    return all_rows


def build_business_targets(rows: List[Dict]) -> Dict[str, List[Dict]]:
    grouped: Dict[str, List[Dict]] = defaultdict(list)
    for row in rows:
        business_id = row.get("business_id")
        if business_id:
            grouped[business_id].append(row)
    return grouped


def write_report(report: Dict, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    logger.info("Report saved: %s", output_path)


async def reparse_businesses(
    service: RoomCollectionService,
    business_ids: List[str],
    sleep_sec: float = 0.0,
) -> Tuple[int, int, List[Dict]]:
    success = 0
    failed = 0
    failures: List[Dict] = []

    for idx, business_id in enumerate(business_ids, start=1):
        try:
            logger.info("Reparsing %s/%s business_id=%s", idx, len(business_ids), business_id)
            await service.collect_by_id(business_id)
            success += 1
        except Exception as e:
            failed += 1
            failures.append({"business_id": business_id, "reason": str(e)})
            logger.exception("Failed to reparse business_id=%s: %s", business_id, e)

        if sleep_sec > 0:
            await asyncio.sleep(sleep_sec)

    return success, failed, failures


async def main() -> None:
    parser = argparse.ArgumentParser(
        description="Re-crawl and re-parse rooms where max_capacity is a manual-review flag."
    )
    parser.add_argument(
        "--flag-value",
        type=int,
        default=RoomCollectionService.MANUAL_REVIEW_FLAG,
        help="Flag value used for parsing failure rows (default: 100)",
    )
    parser.add_argument(
        "--limit-businesses",
        type=int,
        default=0,
        help="Limit number of target businesses (0 means no limit)",
    )
    parser.add_argument(
        "--business-id",
        action="append",
        default=[],
        help="Process specific business IDs only. Can be used multiple times.",
    )
    parser.add_argument(
        "--sleep-sec",
        type=float,
        default=0.0,
        help="Delay between business reparse attempts",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Execute reparse. Without this flag, script runs in dry-run mode.",
    )
    parser.add_argument(
        "--report-path",
        type=str,
        default="",
        help="Optional JSON report path. Defaults to scripts/unresolved/reparse_report_<timestamp>.json",
    )
    args = parser.parse_args()

    load_dotenv()

    before_count = count_flagged_rooms(args.flag_value)
    rows = fetch_flagged_rooms(args.flag_value)
    grouped = build_business_targets(rows)

    target_business_ids = sorted(grouped.keys())
    if args.business_id:
        filter_set = set(args.business_id)
        target_business_ids = [bid for bid in target_business_ids if bid in filter_set]

    if args.limit_businesses and args.limit_businesses > 0:
        target_business_ids = target_business_ids[: args.limit_businesses]

    target_room_count = sum(len(grouped.get(bid, [])) for bid in target_business_ids)

    logger.info("Flag value: %s", args.flag_value)
    logger.info("Rows with flag before reparse: %s", before_count)
    logger.info("Target businesses: %s", len(target_business_ids))
    logger.info("Target rooms: %s", target_room_count)

    if not args.apply:
        logger.info("Dry run mode. Add --apply to execute reparse.")
        return

    service = RoomCollectionService()
    success, failed, failures = await reparse_businesses(
        service=service,
        business_ids=target_business_ids,
        sleep_sec=max(0.0, args.sleep_sec),
    )
    after_count = count_flagged_rooms(args.flag_value)

    report = {
        "executed_at": datetime.now().isoformat(),
        "flag_value": args.flag_value,
        "before_flagged_room_count": before_count,
        "after_flagged_room_count": after_count,
        "target_business_count": len(target_business_ids),
        "target_room_count": target_room_count,
        "success_business_count": success,
        "failed_business_count": failed,
        "failures": failures,
        "target_business_ids": target_business_ids,
    }

    default_report = (
        Path("scripts")
        / "unresolved"
        / f"reparse_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    )
    report_path = Path(args.report_path) if args.report_path else default_report
    write_report(report, report_path)

    logger.info("Reparse completed: success=%s failed=%s", success, failed)
    logger.info(
        "Flagged room delta: %s -> %s (resolved=%s)",
        before_count,
        after_count,
        max(before_count - after_count, 0),
    )


if __name__ == "__main__":
    asyncio.run(main())
