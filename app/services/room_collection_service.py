import logging
import asyncio
import json
import os
import re
import inspect
import tempfile
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional, Any, Tuple
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
                await self.collect_by_id(business_id, source_hint=item)
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
                await self.collect_by_id(business_id, source_hint=item)
                success_count += 1
            except Exception as e:
                logger.error(f"Failed to collect {business_id}: {e}")
                failed_count += 1
                
        return {"success": success_count, "failed": failed_count}

    async def collect_by_id(self, business_id: str, source_hint: Optional[Dict[str, Any]] = None):
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
        await self._save_to_db(business, rooms, parsed_results, source_hint=source_hint)
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

    async def _save_to_db(
        self,
        business: Dict,
        rooms: List[Dict],
        parsed_results: Dict,
        source_hint: Optional[Dict[str, Any]] = None,
    ):
        """Save collected/parsed data to Supabase."""
        
        # 1. Save Branch
        coords = business.get("coordinates")
        display_name = business.get("businessDisplayName") or business.get("name") or business.get("businessId")
        branch_phone_number = self._extract_business_phone_number(
            business,
            rooms,
            source_hint=source_hint,
        )
        place_id = (source_hint or {}).get("placeId")
        if not branch_phone_number and place_id:
            reveal_phone = getattr(self.map_crawler, "reveal_phone_number", None)
            if callable(reveal_phone):
                try:
                    revealed = reveal_phone(str(place_id))
                    if inspect.isawaitable(revealed):
                        revealed = await revealed
                    if isinstance(revealed, str) and revealed.strip():
                        branch_phone_number = revealed.strip()
                except Exception as e:
                    logger.warning(
                        "Phone reveal fallback failed: business_id=%s place_id=%s err=%s",
                        business.get("businessId"),
                        place_id,
                        e,
                    )
        # standby_days 추출: 지점 단위 속성이므로 전체 룸의 파싱 결과 중 첫 번째로 존재하는 값을 사용
        # Rationale: 파서는 룸 단위로 결과를 반환하지만 standbyDays는 사업장(Branch) 단위임.
        branch_standby_days = None
        for room in rooms:
            rid = room.get("bizItemId")
            parsed = parsed_results.get(rid)
            if parsed and parsed.get("standby_days") is not None:
                branch_standby_days = parsed.get("standby_days")
                break

        branch_data = {
            "business_id": business["businessId"],
            "name": display_name,
            "display_name": display_name,
        }

        lat_val, lng_val = self._normalize_coordinates(coords)
        if lat_val is not None:
            branch_data["lat"] = lat_val
        if lng_val is not None:
            branch_data["lng"] = lng_val
        if branch_standby_days is not None:
            branch_data["standby_days"] = branch_standby_days
        if branch_phone_number:
            branch_data["phone_number"] = branch_phone_number
        
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
            parsed_clean_name = parsed.get("clean_name")
            final_room_name = room["name"]
            if isinstance(parsed_clean_name, str):
                candidate = parsed_clean_name.strip()
                if candidate:
                    final_room_name = candidate

            # Extract image URLs
            images = room.get("bizItemResources", [])
            image_urls = [img["resourceUrl"] for img in images] if images else []

            # New Values (MANUAL_REVIEW_FLAG = 100, flags for manual review if parsing fails)
            new_max_cap = parsed.get("max_capacity")
            if new_max_cap is None:
                new_max_cap = self.MANUAL_REVIEW_FLAG
                
            # HACK: [이슈 6 기술부채] recommend_capacity(단일값) 레거시.
            # DTO에서는 제거됐으나 DB 컬럼과 _calculate_capacity_range 의존성 때문에 upsert 유지.
            # 향후 recommend_capacity_range로 완전히 대체 시 이 컬럼 제거 예정.
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

            final_price_config = parsed["price_config"] if "price_config" in parsed else existing_price_config
            if not final_price_config and existing_price_config:
                final_price_config = existing_price_config
            final_base_cap = parsed["base_capacity"] if "base_capacity" in parsed else existing_base_cap
            final_extra_charge = parsed["extra_charge"] if "extra_charge" in parsed else existing_extra_charge

            # Boolean fields fallback
            existing_can_reserve = existing.get("can_reserve_one_hour", True) if existing else True
            parsed_can_reserve = parsed.get("can_reserve_one_hour")
            final_can_reserve = parsed_can_reserve if parsed_can_reserve is not None else existing_can_reserve
            
            existing_requires_call = existing.get("requires_contact_on_sameday", False) if existing else False
            parsed_requires_call = parsed.get("requires_contact_on_sameday")
            if parsed_requires_call is None:
                parsed_requires_call = parsed.get("requires_same_day_contact")
            if parsed_requires_call is None:
                parsed_requires_call = parsed.get("requires_contact_same_day")
            final_requires_call = parsed_requires_call if parsed_requires_call is not None else existing_requires_call

            # Room Data
            room_data = {
                "business_id": business["businessId"],
                "biz_item_id": rid,
                "name": final_room_name,
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
                # NOTE: upsert 키는 실제 DB 컬럼명과 반드시 일치해야 함. AliasChoices는 SELECT에만 효과 있음.
                "requires_contact_on_sameday": final_requires_call,
                "requires_contact_same_day": final_requires_call, # TODO: schema migration 완료 후 old column 제거
                "can_reserve_one_hour": final_can_reserve,
                "image_urls": image_urls  # Save to JSONB column
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

    @staticmethod
    def _coerce_float(value: Any) -> Optional[float]:
        if isinstance(value, bool):
            return None
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, str):
            stripped = value.strip()
            if not stripped:
                return None
            try:
                return float(stripped)
            except ValueError:
                return None
        return None

    @classmethod
    def _normalize_coordinates(cls, coords: Any) -> Tuple[Optional[float], Optional[float]]:
        lat_val: Optional[float] = None
        lng_val: Optional[float] = None

        if isinstance(coords, dict):
            lat_val = cls._coerce_float(coords.get("latitude"))
            if lat_val is None:
                lat_val = cls._coerce_float(coords.get("lat"))
            lng_val = cls._coerce_float(coords.get("longitude"))
            if lng_val is None:
                lng_val = cls._coerce_float(coords.get("lng"))
        elif isinstance(coords, list) and len(coords) >= 2:
            # Naver default list order: [lng, lat]
            lng_val = cls._coerce_float(coords[0])
            lat_val = cls._coerce_float(coords[1])

        if lat_val is not None and lng_val is not None and abs(lat_val) > 90 and abs(lng_val) <= 90:
            lat_val, lng_val = lng_val, lat_val

        if lat_val is not None and abs(lat_val) > 90:
            lat_val = None
        if lng_val is not None and abs(lng_val) > 180:
            lng_val = None

        return lat_val, lng_val

    @classmethod
    def _extract_phone_number_from_payload(cls, payload: Any) -> Optional[str]:
        if payload is None:
            return None

        if isinstance(payload, str):
            stripped = payload.strip()
            if not stripped:
                return None
            try:
                parsed = json.loads(stripped)
            except json.JSONDecodeError:
                cleaned = re.sub(r"https?://\S+", " ", stripped)
                return cls._extract_phone_number_from_text(cleaned)
            return cls._extract_phone_number_from_payload(parsed)

        if isinstance(payload, list):
            for item in payload:
                found = cls._extract_phone_number_from_payload(item)
                if found:
                    return found
            return None

        if isinstance(payload, dict):
            preferred_keys = (
                "phone",
                "phoneNumber",
                "representativePhoneNumber",
                "tel",
                "telephone",
                "mobile",
                "number",
            )
            for key in preferred_keys:
                if key in payload:
                    found = cls._extract_phone_number_from_payload(payload.get(key))
                    if found:
                        return found

            ignored_key_tokens = ("url", "image", "img", "photo", "thumbnail", "resource", "icon", "logo")
            for key, value in payload.items():
                key_lower = str(key).lower()
                if any(token in key_lower for token in ignored_key_tokens):
                    continue
                found = cls._extract_phone_number_from_payload(value)
                if found:
                    return found

        return None

    @staticmethod
    def _extract_phone_number_from_text(text: str) -> Optional[str]:
        if not text:
            return None

        pattern = (
            r"(?<!\d)0507[\s\-]?\d{3,4}[\s\-]?\d{4}(?!\d)"
            r"|(?<!\d)(?:\+82[\s\-]?)?0\d{1,2}[\s\-]?\d{3,4}[\s\-]?\d{4}(?!\d)"
            r"|(?<!\d)(?:1544|1566|1577|1588|1599|1600|1644|1661|1670|1688)[\s\-]?\d{4}(?!\d)"
        )
        best: Optional[Tuple[int, str]] = None

        for match in re.finditer(pattern, text):
            candidate = match.group(0)
            digits = re.sub(r"\D", "", candidate)
            if digits.startswith("82") and len(digits) >= 10:
                digits = "0" + digits[2:]
            if len(digits) < 8 or len(digits) > 12:
                continue

            left = max(0, match.start() - 24)
            right = min(len(text), match.end() + 24)
            window = text[left:right].lower()
            score = 1
            if re.search(r"(전화|문의|연락|콜|tel|phone|contact|call)", window):
                score += 10
            if digits.startswith(("010", "011", "016", "017", "018", "019", "02", "0507")):
                score += 5
            elif digits.startswith(("031", "032", "033", "041", "042", "043", "044", "051", "052", "053", "054", "055", "061", "062", "063", "064", "070")):
                score += 4
            elif digits.startswith(("1544", "1566", "1577", "1588", "1599", "1600", "1644", "1661", "1670", "1688")):
                score += 3

            normalized = re.sub(r"[.\s]+", "-", candidate).strip("-")
            if "-" not in normalized and len(digits) == 8 and digits.startswith(
                ("1544", "1566", "1577", "1588", "1599", "1600", "1644", "1661", "1670", "1688")
            ):
                normalized = f"{digits[:4]}-{digits[4:]}"
            if best is None or score > best[0]:
                best = (score, normalized)

        if best:
            return best[1]
        return None

    @classmethod
    def _extract_business_phone_number(
        cls,
        business: Dict[str, Any],
        rooms: List[Dict[str, Any]],
        source_hint: Optional[Dict[str, Any]] = None,
    ) -> Optional[str]:
        business_candidates = [
            business.get("phoneInformationJson"),
            business.get("phone"),
            business.get("phoneNumber"),
            business.get("telephone"),
            business.get("tel"),
            business,
        ]
        for candidate in business_candidates:
            found = cls._extract_phone_number_from_payload(candidate)
            if found:
                return found

        if source_hint:
            found = cls._extract_phone_number_from_payload(source_hint)
            if found:
                return found

        for room in rooms:
            room_candidates = [
                room.get("phone"),
                room.get("phoneNumber"),
                room.get("telephone"),
                room.get("tel"),
                room.get("bookingPrecautionJson"),
                room.get("extraDescJson"),
                room.get("desc"),
            ]
            for candidate in room_candidates:
                found = cls._extract_phone_number_from_payload(candidate)
                if found:
                    return found
        return None


