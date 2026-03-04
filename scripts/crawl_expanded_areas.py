"""
신촌역 포함 확장 크롤링 실행 스크립트.

Usage:
    python scripts/crawl_expanded_areas.py [--dry-run]

--dry-run: 크롤링만 하고 DB 저장하지 않음 (기본: 저장함)
"""
import asyncio
import json
import logging
import sys
from datetime import datetime
from pathlib import Path

# 프로젝트 루트를 sys.path에 추가
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

    if dry_run:
        logger.info("=== DRY RUN: 크롤링만 실행, DB 저장 안 함 ===")
        # 크롤러만 직접 호출
        from app.core.constants import PRIORITY_AREA_QUERIES
        all_items = {}
        for query in PRIORITY_AREA_QUERIES:
            logger.info(f"Searching: {query}")
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
        result_path.write_text(json.dumps({
            "total_unique": len(all_items),
            "business_ids": sorted(all_items.keys()),
            "items": list(all_items.values()),
        }, ensure_ascii=False, indent=2), encoding="utf-8")
        logger.info(f"Dry-run 결과 저장: {result_path}")
        logger.info(f"발견된 고유 업소 수: {len(all_items)}")
    else:
        logger.info("=== 전체 크롤링 + DB 저장 실행 ===")
        result = await service.collect_priority_areas()
        result_path = Path("logs") / f"crawl_expanded_{datetime.now().strftime('%Y-%m-%d_%H%M%S')}.json"
        result_path.parent.mkdir(parents=True, exist_ok=True)
        # set → list 변환
        serializable = json.loads(json.dumps(result, default=str))
        result_path.write_text(json.dumps(serializable, ensure_ascii=False, indent=2), encoding="utf-8")
        logger.info(f"크롤링 결과 저장: {result_path}")
        logger.info(f"성공: {result.get('success')}, 실패: {result.get('failed')}, 건너뜀: {result.get('skipped')}")


if __name__ == "__main__":
    asyncio.run(main())
