import asyncio
import argparse
import logging
import sys
import os

# Add project root to path for module discovery
sys.path.append(os.getcwd())

from app.services.room_collection_service import RoomCollectionService
from dotenv import load_dotenv

# Logging configuration
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

async def main():
    parser = argparse.ArgumentParser(description="Naver Rehearsal Room Collector")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--query", type=str, help="Search query (e.g., '홍대 합주실')")
    group.add_argument("--id", type=str, help="Specific Business ID to collect")
    group.add_argument("--auto", action="store_true", help="Auto-collect nationwide (Seoul + Major Cities)")
    
    args = parser.parse_args()

    # Load environment variables (.env)
    load_dotenv()

    service = RoomCollectionService()

    try:
        if args.id:
            logger.info(f"Collecting specific business ID: {args.id}")
            await service.collect_by_id(args.id)
            logger.info("Collection completed successfully.")
        
        elif args.query:
            logger.info(f"Collecting by query: {args.query}")
            result = await service.collect_by_query(args.query)
            logger.info(f"Collection Report: {result}")
            
        elif args.auto:
            logger.info("Starting Auto Nationwide Collection...")
            result = await service.collect_all_regions()
            logger.info(f"Nationwide Collection Report: {result}")
            
    except Exception as e:
        logger.error(f"Collection failed: {e}")
        sys.exit(1)

if __name__ == "__main__":
    # if sys.platform.startswith('win'):
    #     # Windows requires SelectorEventLoopPolicy for Playwright
    #     asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main())
