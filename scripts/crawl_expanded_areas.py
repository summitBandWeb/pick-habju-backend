"""
Expanded area crawl script.

Usage:
    python scripts/crawl_expanded_areas.py [--dry-run]

--dry-run: run crawl only and skip DB write.
"""
import asyncio
import json
import logging
import sys
from datetime import datetime
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services.room_collection_service import RoomCollectionService

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


async def main():
    dry_run = "--dry-run" in sys.argv
    service = RoomCollectionService()

    try:
        if dry_run:
            logger.info("=== DRY RUN: crawl only, no DB write ===")
            from app.core.constants import PRIORITY_AREA_QUERIES

            all_items = {}
            for query in PRIORITY_AREA_QUERIES:
                logger.info("Searching: %s", query)
                try:
                    results = await service.map_crawler.search_rehearsal_rooms(query)
                except Exception:
                    logger.exception("Search failed for query=%s; continuing dry-run", query)
                    results = []

                for item in results:
                    bid = item.get("id")
                    if bid:
                        all_items[str(bid)] = {
                            "id": str(bid),
                            "name": item.get("name", ""),
                            "address": item.get("address", ""),
                            "bookingBusinessId": item.get("bookingBusinessId"),
                            "source_query": query,
                        }
                await asyncio.sleep(2)

            result_path = Path("logs") / f"crawl_expanded_{datetime.now().strftime('%Y-%m-%d_%H%M%S')}.json"
            result_path.parent.mkdir(parents=True, exist_ok=True)
            result_path.write_text(
                json.dumps(
                    {
                        "total_unique": len(all_items),
                        "business_ids": sorted(all_items.keys()),
                        "items": list(all_items.values()),
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
            logger.info("Dry-run result saved: %s", result_path)
            logger.info("Total unique businesses: %s", len(all_items))
        else:
            logger.info("=== Full crawl + DB write ===")
            result = await service.collect_priority_areas()
            result_path = Path("logs") / f"crawl_expanded_{datetime.now().strftime('%Y-%m-%d_%H%M%S')}.json"
            result_path.parent.mkdir(parents=True, exist_ok=True)
            result_path.write_text(
                json.dumps(
                    result,
                    ensure_ascii=False,
                    indent=2,
                    default=lambda obj: sorted(obj) if isinstance(obj, set) else str(obj),
                ),
                encoding="utf-8",
            )
            logger.info("Crawl result saved: %s", result_path)
            logger.info(
                "success=%s failed=%s skipped=%s",
                result.get("success"),
                result.get("failed"),
                result.get("skipped"),
            )
    finally:
        crawler = getattr(service, "map_crawler", None)
        if crawler and hasattr(crawler, "close"):
            crawler.close()


if __name__ == "__main__":
    asyncio.run(main())
