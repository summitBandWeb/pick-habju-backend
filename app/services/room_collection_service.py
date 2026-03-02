import logging
import asyncio
import json
import os
import re
import tempfile
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional, Any
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
    # Rationale: 100명을 수용하는 합주실은 현실적으로 없으므로 수동 검토 필요 목적으로 식별 가능
    MANUAL_REVIEW_FLAG = 100

    def __init__(self):
        self.map_crawler = NaverMapCrawler()
        self.room_fetcher = NaverRoomFetcher()
        self.parser_service = RoomParserService()
        self.supabase = get_supabase_client()

    async def collect_by_query(self, query: str) -> Dict[str, Any]:
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
        failures: List[Dict[str, str]] = []

        for item in search_results:
            try:
                business_id = item.get("id")
                if not business_id:
                    raise ValueError("missing business id in search result")
                await self.collect_by_id(business_id)
                success_count += 1
            except Exception as e:
                logger.error(f"Failed to collect item={item}: {e}")
                failed_count += 1
                failures.append({
                    "business_id": item.get("id", ""),
                    "business_name": item.get("name", ""),
                    "reason": str(e),
                })
                
        return {
            "query": query,
            "total": len(search_results),
            "success": success_count,
            "failed": failed_count,
            "failures": failures,
        }

    async def collect_all_regions(self) -> Dict[str, Any]:
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
        failures: List[Dict[str, str]] = []
        
        # 2. Process each found business
        total_items = len(all_items)
        for idx, item in enumerate(all_items):
            try:
                business_id = item.get("id")
                if not business_id:
                    raise ValueError("missing business id in crawl result")
                logger.info(f"Processing {idx+1}/{total_items}: {item['name']} ({business_id})")
                await self.collect_by_id(business_id)
                success_count += 1
            except Exception as e:
                logger.error(f"Failed to collect item={item}: {e}")
                failed_count += 1
                failures.append({
                    "business_id": item.get("id", ""),
                    "business_name": item.get("name", ""),
                    "reason": str(e),
                })
                
        return {
            "total": total_items,
            "success": success_count,
            "failed": failed_count,
            "failures": failures,
        }

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
        # Rationale: business.desc에 가게 전체 장비/규칙이 담겨 있으므로
        #            개별 룸 파싱 시 컨텍스트로 함께 전달하여 정확도를 높임
        business_desc = business.get("desc") or ""
        parse_items = []
        for room in rooms:
            parse_items.append({
                "id": room["bizItemId"],
                "name": room["name"],
                "desc": room.get("desc"),
                "business_desc": business_desc
            })
        
        # Chunk items for parallel processing
        parsed_results = await self._parse_with_concurrency(parse_items)

        # 3. Save to DB (Branch -> Room(with images))
        await self._save_to_db(business, rooms, parsed_results)
        logger.info(f"Successfully saved business {business_id} with {len(rooms)} rooms")

        # 4. Export unresolved items (Phase 6: Manual verification queue)
        await self._export_unresolved(business, rooms, parsed_results)

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
            "display_name": business.get("businessDisplayName"),  # v2.0.0: 노출용 이름
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
            new_max_cap = parsed.get("max_capacity")
            if new_max_cap is None:
                new_max_cap = self.MANUAL_REVIEW_FLAG
                
            new_rec_cap = parsed.get("recommend_capacity")
            if new_rec_cap is None:
                new_rec_cap = self.MANUAL_REVIEW_FLAG
                
            new_price = self._extract_price(room)
            new_price_config = parsed.get("price_config")

            # [Logic] Preserve existing valid values if new ones are defaults (0 or 1)
            final_max_cap = new_max_cap
            final_rec_cap = new_rec_cap
            final_price = new_price
            final_price_config = new_price_config

            if existing:
                existing_max = existing.get("max_capacity", 0)
                existing_rec = existing.get("recommend_capacity", 0)

                # [Logic] 기존 값이 유효하고(>1), 새 값이 기본값(1)이거나 수동검토플래그(100)인 경우 기존 값 보존
                # 단, 기존 값 자체가 100인 경우는 제외
                if (new_max_cap <= 1 or new_max_cap == self.MANUAL_REVIEW_FLAG) and existing_max > 1 and existing_max != self.MANUAL_REVIEW_FLAG:
                    final_max_cap = existing_max
                
                if (new_rec_cap <= 1 or new_rec_cap == self.MANUAL_REVIEW_FLAG) and existing_rec > 1 and existing_rec != self.MANUAL_REVIEW_FLAG:
                    final_rec_cap = existing_rec

                # If new price is 0/None but existing is valid, keep existing
                # Note: self._extract_price returns None if missing, which is not > 0.
                existing_price = existing.get("price_per_hour")
                if (not new_price or new_price == 0) and existing_price and existing_price > 0:
                    final_price = existing_price

            # Preserve existing JSON values unless parser explicitly provides replacements.
            existing_price_config = existing.get("price_config", []) if existing else []
            existing_base_cap = existing.get("base_capacity") if existing else None
            existing_extra_charge = existing.get("extra_charge") if existing else None
            structured_extra_charge = self._extract_structured_extra_charge(room)

            final_price_config = parsed["price_config"] if "price_config" in parsed else existing_price_config
            if not final_price_config and existing_price_config:
                final_price_config = existing_price_config
            final_base_cap = parsed["base_capacity"] if "base_capacity" in parsed else existing_base_cap
            if "extra_charge" in parsed:
                final_extra_charge = parsed["extra_charge"]
            elif structured_extra_charge is not None:
                final_extra_charge = structured_extra_charge
            else:
                final_extra_charge = existing_extra_charge

            # Boolean fields fallback
            existing_can_reserve = existing.get("can_reserve_one_hour", True) if existing else True
            parsed_can_reserve = parsed.get("can_reserve_one_hour")
            structured_can_reserve = self._extract_structured_can_reserve_one_hour(room)
            if structured_can_reserve is not None:
                final_can_reserve = structured_can_reserve
            elif parsed_can_reserve is not None:
                final_can_reserve = parsed_can_reserve
            else:
                final_can_reserve = existing_can_reserve
            
            existing_requires_call = existing.get("requires_call_on_sameday", False) if existing else False
            parsed_requires_call = parsed.get("requires_call_on_same_day")
            final_requires_call = parsed_requires_call if parsed_requires_call is not None else existing_requires_call

            # Room Data
            room_data = {
                "business_id": business["businessId"],
                "biz_item_id": rid,
                "name": room["name"],
                "price_per_hour": final_price,
                # Schema constraint: Default to 1 if null
                "max_capacity": final_max_cap,
                "recommend_capacity": final_rec_cap,
                # [v2.0.0] 신규 필드: 권장 인원 범위 및 동적 가격 정책
                "recommend_capacity_range": self._calculate_capacity_range(
                    parsed.get("recommend_capacity_range"),
                    final_rec_cap,
                    final_max_cap,
                    final_base_cap,
                    final_extra_charge
                ),
                "price_config": final_price_config,
                "base_capacity": final_base_cap,
                "extra_charge": final_extra_charge,
                "requires_call_on_sameday": final_requires_call,
                "can_reserve_one_hour": final_can_reserve,
                "image_urls": image_urls  # Save to JSONB column
            }
            
            # Upsert Room
            self.supabase.table("room").upsert(room_data).execute()

    def _extract_structured_can_reserve_one_hour(self, room: Dict) -> Optional[bool]:
        """Infer one-hour reservation availability from structured booking policy fields."""
        unit_code = (room.get("bookingTimeUnitCode") or "").upper()
        min_booking_time = room.get("minBookingTime")

        if isinstance(min_booking_time, (int, float)):
            if "MIN" in unit_code:
                return min_booking_time <= 60
            return min_booking_time <= 1

        booking_count_setting = room.get("bookingCountSettingJson")
        if isinstance(booking_count_setting, dict):
            for key in ("minBookingTime", "minimumBookingTime", "minTime", "minimumTime"):
                value = booking_count_setting.get(key)
                if isinstance(value, (int, float)):
                    if "MIN" in unit_code:
                        return value <= 60
                    return value <= 1

        return None

    def _extract_structured_extra_charge(self, room: Dict) -> Optional[int]:
        """Extract extra charge from structured JSON fields before text/LLM fallback."""
        extra_fee_setting = room.get("extraFeeSettingJson")
        if isinstance(extra_fee_setting, str):
            try:
                extra_fee_setting = json.loads(extra_fee_setting)
            except json.JSONDecodeError:
                extra_fee_setting = None

        if not isinstance(extra_fee_setting, dict):
            return None

        key_hints = (
            "extrafee",
            "extra_fee",
            "extracharge",
            "extra_charge",
            "additionalfee",
            "additional_fee",
            "surcharge",
            "amount",
        )

        def walk(obj: Any) -> Optional[int]:
            if isinstance(obj, dict):
                for key, value in obj.items():
                    lowered = str(key).lower()
                    if any(hint in lowered for hint in key_hints):
                        parsed = self._coerce_int(value)
                        if parsed is not None:
                            return parsed
                    nested = walk(value)
                    if nested is not None:
                        return nested
            elif isinstance(obj, list):
                for item in obj:
                    nested = walk(item)
                    if nested is not None:
                        return nested
            return None

        return walk(extra_fee_setting)

    @staticmethod
    def _coerce_int(value: Any) -> Optional[int]:
        """Best-effort conversion of number-like values to int."""
        if isinstance(value, bool):
            return None
        if isinstance(value, int):
            return value
        if isinstance(value, float):
            return int(value)
        if isinstance(value, str):
            digits = re.sub(r"[^\d]", "", value)
            if digits:
                try:
                    return int(digits)
                except ValueError:
                    return None
        return None

    def _extract_price(self, room: Dict) -> Optional[int]:
        """Extract pricing information."""
        min_max = room.get("minMaxPrice")
        if not min_max:
            return None
        # Use minPrice as the base price
        return min_max.get("minPrice")

    def _calculate_capacity_range(
        self,
        parsed_range: Optional[List[int]],
        rec_cap: int,
        max_cap: int,
        base_cap: Optional[int],
        extra_charge: Optional[int]
    ) -> List[int]:
        """추가 요금 유무에 따라 권장 인원 범위 계산

        Args:
            parsed_range: LLM/정규식이 파싱한 범위 ([min, max] 형태)
            rec_cap: 권장 인원 수
            max_cap: 최대 인원 수
            base_cap: 기준 인원 수 (추가 요금 계산 기준)
            extra_charge: 추가 요금 (원)

        Returns:
            [min, max] 형태의 권장 인원 범위 리스트

        Rationale:
            1. 파싱된 범위가 유효하면 우선 사용 (단 합리적 범위로 clamp)
            2. 추가 요금 발생 시 [base_cap, max_cap]
            3. 추가 요금 없을 시 [rec_cap, rec_cap + 2] (최대 max_cap)
        """
        # 1. 파싱된 범위 검증 후 우선 사용
        # 조건: 2개 숫자(int 또는 float), min <= max, 합주실 현실적 범위(1~50명 이내)
        # NOTE: LLM 파서가 float(예: 4.0)을 반환할 수 있으므로 int/float 모두 허용
        if (
            isinstance(parsed_range, list)
            and len(parsed_range) == 2
            and all(isinstance(v, (int, float)) for v in parsed_range)
            and parsed_range[0] <= parsed_range[1]
            and 1 <= parsed_range[0] and parsed_range[1] <= 50
        ):
            # float → int 변환 및 합리적 범위로 clamp
            clamped_min = max(int(parsed_range[0]), 1)
            clamped_max = min(int(parsed_range[1]), max_cap) if max_cap > 0 else int(parsed_range[1])
            # clamp 후에도 min <= max 보장
            clamped_max = max(clamped_max, clamped_min)
            return [clamped_min, clamped_max]

        # --- Sentinel 방어 ---
        # NOTE: MANUAL_REVIEW_FLAG(100)이 rec_cap/max_cap/base_cap에 들어오면
        #        [100, 102] 같은 비현실적 범위가 반환되므로 현실적 상한(50)으로 clamp
        MAX_REALISTIC_CAP = 50
        if max_cap >= self.MANUAL_REVIEW_FLAG:
            max_cap = MAX_REALISTIC_CAP
        if rec_cap >= self.MANUAL_REVIEW_FLAG:
            rec_cap = MAX_REALISTIC_CAP
        if base_cap and base_cap >= self.MANUAL_REVIEW_FLAG:
            base_cap = MAX_REALISTIC_CAP

        # 2. 추가 요금 있는 경우
        if extra_charge and extra_charge > 0 and base_cap:
            # min: base_cap, max: max_cap
            # 단 max_cap < base_cap인 비정상 데이터 방어
            real_max = max(max_cap, base_cap)
            return [base_cap, real_max]
            
        # 3. 추가 요금 없는 경우 (기본)
        # min: rec_cap, max: rec_cap + 2
        # 단 max_cap을 넘지 않도록 제한
        min_c = rec_cap
        max_c = min(rec_cap + 2, max_cap)
        
        # 만약 rec_cap + 2 > max_cap 이라면 max_c가 min_c보다 작아지는 경우 방어
        # (예: rec=5, max=5 -> min=5, max=5)
        max_c = max(max_c, min_c)
        
        return [min_c, max_c]

    async def _export_unresolved(self, business: Dict, rooms: List[Dict], parsed_results: Dict):
        """
        Export unresolved parsing results to JSON file for manual LLM verification.

        Phase 6: When parsing is incomplete (especially when no capacity info is found),
        export the original crawled text to a JSON file for later manual verification.
        """
        unresolved_items = []

        for room in rooms:
            rid = room["bizItemId"]
            parsed = parsed_results.get(rid, {})

            # Identify unresolved items based on capacity parsing failures
            max_capacity = parsed.get("max_capacity")
            failure_reason = None

            if max_capacity is None:
                failure_reason = "no_capacity_info"
            elif max_capacity == self.MANUAL_REVIEW_FLAG:
                failure_reason = "manual_review_flag"

            # Only export if there's a failure reason
            if failure_reason:
                unresolved_item = {
                    "business_id": business["businessId"],
                    "business_name": business["businessDisplayName"],
                    "biz_item_id": rid,
                    "raw_name": room["name"],
                    "raw_desc": room.get("desc"),
                    "parsed_result": parsed,
                    "failure_reason": failure_reason,
                    "price_per_hour": self._extract_price(room),
                    "exported_at": datetime.now().isoformat()
                }
                unresolved_items.append(unresolved_item)

        # If there are unresolved items, export them
        if unresolved_items:
            # 로컬 환경에서 호출 시 경로 설정 가능. 기본값은 프로젝트 루트/scripts/unresolved
            default_dir = Path(__file__).parent.parent.parent / "scripts" / "unresolved"
            export_dir = Path(os.getenv("UNRESOLVED_EXPORT_DIR", str(default_dir)))
            export_dir.mkdir(parents=True, exist_ok=True)

            # Generate filename with current date
            date_str = datetime.now().strftime("%Y%m%d")
            export_file = export_dir / f"unresolved_{date_str}.json"

            # Load existing data if file exists, otherwise start with empty list
            existing_data = []
            if export_file.exists():
                try:
                    with open(export_file, "r", encoding="utf-8") as f:
                        existing_data = json.load(f)
                except Exception as e:
                    logger.warning(f"Failed to read existing unresolved file: {e}")

            # Append new unresolved items with duplicate check
            existing_ids = {item["biz_item_id"] for item in existing_data}
            new_items = [item for item in unresolved_items if item["biz_item_id"] not in existing_ids]

            if new_items:
                existing_data.extend(new_items)

                # Atomic write: temp file 후 rename으로 중간 상태 방지
                tmp_fd, tmp_path = tempfile.mkstemp(
                    dir=str(export_dir), suffix=".tmp"
                )
                try:
                    with os.fdopen(tmp_fd, "w", encoding="utf-8") as f:
                        json.dump(existing_data, f, ensure_ascii=False, indent=2)
                    # os.replace는 원자적(같은 파일시스템 상)
                    os.replace(tmp_path, str(export_file))
                except Exception:
                    # 실패 시 임시 파일 정리
                    if os.path.exists(tmp_path):
                        os.unlink(tmp_path)
                    raise

                logger.info(f"Exported {len(new_items)} new unresolved items to {export_file} (skipped {len(unresolved_items) - len(new_items)} duplicates)")
            else:
                logger.debug(f"All {len(unresolved_items)} items were already in unresolved list. Skipping export.")



