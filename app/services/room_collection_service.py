import logging
import asyncio
from typing import List, Dict, Optional
from app.crawler.naver_map_crawler import NaverMapCrawler
from app.crawler.naver_room_fetcher import NaverRoomFetcher
from app.services.room_parser_service import RoomParserService
from app.core.supabase_client import get_supabase_client

logger = logging.getLogger(__name__)

class RoomCollectionService:
    """Service for collecting and parsing rehearsal room data."""
    
    # Tunable parameters for concurrency
    BATCH_SIZE = 5           # Number of rooms per LLM batch call
    MAX_CONCURRENT_BATCHES = 3  # Number of parallel LLM calls
    
    # Capacity value indicating LLM parsing failure - flags for manual review
    # Rationale: 100명을 수용하는 합주실은 현실적으로 없으므로 수동 검토 필요 항목으로 식별 가능
    MANUAL_REVIEW_FLAG = 100

    def __init__(self):
        self.map_crawler = NaverMapCrawler()
        self.room_fetcher = NaverRoomFetcher()
        self.parser_service = RoomParserService()
        self.supabase = get_supabase_client()

    async def collect_by_query(self, query: str) -> Dict[str, int]:
        """
        Search and collect rooms by query keyword.
        
        Args:
            query: Search keyword (e.g., "Hongdae practice room")
            
        Returns:
            Dict containing counts of successful and failed collections.
        """
        logger.info(f"Starting collection for query: {query}")
        
        # 1. 지도 검색으로 ID 확보
        search_results = await self.map_crawler.search_rehearsal_rooms(query)
        logger.info(f"Found {len(search_results)} businesses for {query}")
        
        success_count = 0
        failed_count = 0

        for item in search_results:
            business_id = item["id"]
            try:
                await self.collect_by_id(business_id)
                success_count += 1
            except Exception as e:
                logger.error(f"Failed to collect {business_id}: {e}")
                failed_count += 1
                
        return {"success": success_count, "failed": failed_count}

    async def collect_all_regions(self) -> Dict[str, int]:
        """
        Collect rooms from all major regions nationwide.
        """
        logger.info("Starting nationwide collection...")
        
        # 1. Crawl all regions
        # Note: crawl_all_regions returns list of Item dicts, but search_rehearsal_rooms returns same structure.
        # We assume crawl_all_regions returns a list of items similar to search results.
        all_items = await self.map_crawler.crawl_all_regions()
        logger.info(f"Total unique businesses found nationwide: {len(all_items)}")
        
        success_count = 0
        failed_count = 0
        
        # 2. Process each found business
        total_items = len(all_items)
        for idx, item in enumerate(all_items):
            business_id = item["id"]
            try:
                logger.info(f"Processing {idx+1}/{total_items}: {item['name']} ({business_id})")
                await self.collect_by_id(business_id)
                success_count += 1
            except Exception as e:
                logger.error(f"Failed to collect {business_id}: {e}")
                failed_count += 1
                
        return {"success": success_count, "failed": failed_count}

    async def collect_by_id(self, business_id: str):
        """Collect and save room information for a specific Business ID."""
        logger.info(f"Collecting business_id: {business_id}")

        # 1. Fetch Full Info
        data = await self.room_fetcher.fetch_full_info(business_id)
        if not data:
            raise ValueError(f"No data found for business {business_id}")

        business = data["business"]
        rooms = data["rooms"]
        
        if not rooms:
            logger.warning(f"No rooms found for business {business_id}")
            return

        # 2. LLM Parsing (Batch with Concurrency)
        parse_items = []
        for room in rooms:
            parse_items.append({
                "id": room["bizItemId"],
                "name": room["name"],
                "desc": room.get("desc")
            })
        
        # Chunk items for parallel processing
        parsed_results = await self._parse_with_concurrency(parse_items)

        # 3. Save to DB (Branch -> Room(with images))
        await self._save_to_db(business, rooms, parsed_results)
        logger.info(f"Successfully saved business {business_id} with {len(rooms)} rooms")

    async def _parse_with_concurrency(self, items: List[Dict]) -> Dict[str, Dict]:
        """Parse items in concurrent batches."""
        if not items:
            return {}
            
        # Chunk items
        chunks = [items[i:i + self.BATCH_SIZE] for i in range(0, len(items), self.BATCH_SIZE)]
        logger.info(f"Splitting {len(items)} items into {len(chunks)} chunks (batch size: {self.BATCH_SIZE})")
        
        # Semaphore for concurrency limit
        semaphore = asyncio.Semaphore(self.MAX_CONCURRENT_BATCHES)
        
        async def parse_chunk(chunk: List[Dict]) -> Dict[str, Dict]:
            async with semaphore:
                return await self.parser_service.parse_room_desc_batch(chunk)
        
        # Run all chunks concurrently (limited by semaphore)
        results = await asyncio.gather(*[parse_chunk(c) for c in chunks])
        
        # Merge results
        merged = {}
        for r in results:
            merged.update(r)
        return merged

    async def _save_to_db(self, business: Dict, rooms: List[Dict], parsed_results: Dict):
        """Save collected/parsed data to Supabase."""
        
        # 1. Save Branch
        coords = business.get("coordinates")
        branch_data = {
            "business_id": business["businessId"],
            "name": business["businessDisplayName"],
            "lat": coords.get("latitude") if coords else None,
            "lng": coords.get("longitude") if coords else None,
        }
        
        # Upsert Branch
        self.supabase.table("branch").upsert(branch_data).execute()

        # [Data Preservation] Fetch existing rooms for this business to check for manual overrides
        try:
            existing_resp = self.supabase.table("room").select("*").eq("business_id", business["businessId"]).execute()
            existing_map = {r["biz_item_id"]: r for r in existing_resp.data}
        except Exception as e:
            logger.warning(f"Failed to fetch existing rooms: {e}")
            existing_map = {}

        # 2. Save Room (including images)
        for room in rooms:
            rid = room["bizItemId"]
            parsed = parsed_results.get(rid, {})
            existing = existing_map.get(rid)

            # Extract image URLs
            images = room.get("bizItemResources", [])
            image_urls = [img["resourceUrl"] for img in images] if images else []

            # New Values (MANUAL_REVIEW_FLAG = 100, flags for manual review if parsing fails)
            new_max_cap = parsed.get("max_capacity") or self.MANUAL_REVIEW_FLAG
            new_rec_cap = parsed.get("recommend_capacity") or self.MANUAL_REVIEW_FLAG
            new_price = self._extract_price(room)

            # [Logic] Preserve existing valid values if new ones are defaults (0 or 1)
            final_max_cap = new_max_cap
            final_rec_cap = new_rec_cap
            final_price = new_price

            if existing:
                # If new max_capacity is default(1) but existing is valid(>1), keep existing
                if new_max_cap <= 1 and existing.get("max_capacity", 0) > 1:
                    final_max_cap = existing["max_capacity"]
                
                # If new recommend_capacity is default(1) but existing is valid(>1), keep existing
                if new_rec_cap <= 1 and existing.get("recommend_capacity", 0) > 1:
                    final_rec_cap = existing["recommend_capacity"]

                # If new price is 0/None but existing is valid, keep existing
                # Note: self._extract_price returns None if missing, which is not > 0.
                existing_price = existing.get("price_per_hour")
                if (not new_price or new_price == 0) and existing_price and existing_price > 0:
                    final_price = existing_price

            # Room Data
            room_data = {
                "business_id": business["businessId"],
                "biz_item_id": rid,
                "name": room["name"],
                "price_per_hour": final_price,
                # Schema constraint: Default to 1 if null
                "max_capacity": final_max_cap,
                "recommend_capacity": final_rec_cap,
                # "created_at": "now()", # Schema does not have created_at
                "base_capacity": parsed.get("base_capacity"),
                "extra_charge": parsed.get("extra_charge"),
                "requires_call_on_sameday": parsed.get("requires_call_on_same_day") or False,
                "image_urls": image_urls # Save to JSONB column
            }
            
            # Upsert Room
            self.supabase.table("room").upsert(room_data).execute()

    def _extract_price(self, room: Dict) -> Optional[int]:
        """Extract pricing information."""
        min_max = room.get("minMaxPrice")
        if not min_max:
            return None
        # Use minPrice as the base price
        return min_max.get("minPrice")
