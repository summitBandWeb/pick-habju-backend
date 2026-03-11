import logging
import asyncio
import json
import os
import re
import random
import inspect
import tempfile
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional, Any, Tuple
from app.crawler.naver_map_crawler import NaverMapCrawler
from app.crawler.naver_room_fetcher import NaverRoomFetcher
from app.services.room_parser_service import RoomParserService
from app.core.constants import PRIORITY_AREA_QUERIES
from app.core.supabase_client import get_supabase_client
from app.core.name_utils import normalize_name_token

logger = logging.getLogger(__name__)

class RoomCollectionService:
    """합주실 데이터 수집 및 파싱 서비스"""

    # 동시성 튜닝 파라미터
    BATCH_SIZE = 5
    MAX_CONCURRENT_BATCHES = 3
    DEFAULT_PRIORITY_AREA_QUERIES = list(PRIORITY_AREA_QUERIES)
    
    # 파싱 실패 시 수동 검토 플래그 값
    # Rationale: 100명을 수용하는 합주실은 현실적으로 없으므로 수동 검토 필요 목적으로 식별 가능
    MANUAL_REVIEW_FLAG = 100
    MAX_BUSINESS_DESC_CHARS = int(os.getenv("MAX_BUSINESS_DESC_CHARS", "1200"))
    PRICE_MATCH_TOLERANCE = 1000
    # 룸 단위 수용 인원 정보가 없을 때의 글로벌 fallback 규칙
    # 운영 기준:
    # - 7,000~9,999원 → 2~4명 (소형룸)
    # - 10,000~14,999원 → 4~5명
    # - 15,000~19,999원 → 7~8명
    # - 20,000원 이상 → 10명 이상
    PRICE_BAND_CAPACITY_DEFAULTS: List[Dict[str, Any]] = [
        {
            "name": "7k_10k",
            "min_price": 7000,
            "max_price": 9999,
            "max_capacity": 4,
            "recommend_capacity": 2,
        },
        {
            "name": "10k_15k",
            "min_price": 10000,
            "max_price": 14999,
            "max_capacity": 5,
            "recommend_capacity": 4,
        },
        {
            "name": "15k_20k",
            "min_price": 15000,
            "max_price": 19999,
            "max_capacity": 8,
            "recommend_capacity": 7,
        },
        {
            "name": "20k_plus",
            "min_price": 20000,
            "max_price": None,  # open upper bound
            "max_capacity": 11,
            "recommend_capacity": 10,
        },
    ]
    PRICE_CAPACITY_RULES: Dict[str, List[Dict[str, Any]]] = {
        # 그루브 사당점 (수동 기준선)
        "sadang": [
            {"price": 8000, "max_capacity": 4, "recommend_capacity": 2, "recommend_range": [1, 2]},
            {"price": 10000, "max_capacity": 6, "recommend_capacity": 3, "recommend_range": [1, 3]},
        ],
        # 비쥬 합주실 (수동 기준선)
        "522011": [
            {"price": 15000, "max_capacity": 10, "recommend_capacity": 5, "recommend_range": [4, 6]},
        ],
        "706924": [
            {"price": 12000, "max_capacity": 8, "recommend_capacity": 4, "recommend_range": [3, 5]},
        ],
        "917236": [
            {"price": 20000, "max_capacity": 12, "recommend_capacity": 6, "recommend_range": [4, 6]},
        ],
        # 준사운드 사당점 (수동 기준선)
        "1384809": [
            {"price": 15000, "max_capacity": 10, "recommend_capacity": 5, "recommend_range": [3, 5]},
        ],
    }
    REHEARSAL_KEYWORDS: Tuple[str, ...] = (
        "합주실",
        "합주",
        "밴드합주",
    )
    REPRESENTATIVE_KEYWORD_FIELDS: Tuple[str, ...] = (
        "representativeKeyword",
        "representativeKeywords",
        "keywords",
        "tags",
        "hashtagList",
        "hashtag",
    )
    # 강제 제외: 합주와 다른 장르/용도 — 합주 키워드가 함께 있어도 무조건 필터링
    NON_REHEARSAL_ROOM_NAME_KEYWORDS: Tuple[str, ...] = (
        # 교육/레슨
        "레슨", "lesson", "수업", "클래스", "원데이",
        # 악기 대여
        "기타 대여", "베이스 대여", "앰프 대여", "드럼스틱", "악기 대여",
        # 비음악 용도
        "무용", "댄스", "요가", "필라테스",
        # 개인연습/비합주
        "피아노", "그랜드피아노", "화상면접", "면접",
        # 기타
        "파티룸", "촬영", "세미나",
    )
    # 안내성 항목: 실제 룸이 아닌 예약 안내/이벤트/견적 등의 더미 항목
    NON_ROOM_NAME_KEYWORDS: Tuple[str, ...] = (
        "당일 예약", "전화 문의", "이벤트 할인", "이벤트 예약",
        "셀프견적", "견적", "공지", "안내",
    )
    # 조건부 허용: 음악 후반작업 — 합주실에서 흔히 제공하므로 합주 키워드 공존 시 보존
    NON_REHEARSAL_SOFT_KEYWORDS: Tuple[str, ...] = (
        "레코딩", "recording", "녹음", "믹싱", "마스터링",
    )

    def __init__(self):
        self.map_crawler = NaverMapCrawler()
        self.room_fetcher = NaverRoomFetcher()
        self.parser_service = RoomParserService()
        self.supabase = get_supabase_client()
        self._unsupported_branch_columns: set[str] = set()
        self._unsupported_room_columns: set[str] = set()
        self._source_item_hints: Dict[str, Dict[str, Any]] = {}

    @classmethod
    def _resolve_priority_area_queries(cls, area_queries: Optional[List[str]]) -> List[str]:
        if area_queries:
            return [q.strip() for q in area_queries if isinstance(q, str) and q.strip()]

        env_raw = os.getenv("PRIORITY_AREA_QUERIES")
        if env_raw:
            return [q.strip() for q in env_raw.split(",") if q.strip()]

        return list(cls.DEFAULT_PRIORITY_AREA_QUERIES)

    async def collect_priority_areas(
        self,
        area_queries: Optional[List[str]] = None,
        max_targets: Optional[int] = None,
    ) -> Dict[str, Any]:
        """설정된 우선 역세권에서만 룸 데이터를 수집한다."""
        queries = self._resolve_priority_area_queries(area_queries)
        if not queries:
            raise ValueError("No priority area queries configured")

        logger.info("Starting priority-area collection for %s queries", len(queries))
        query_reports: List[Dict[str, Any]] = []
        dedup_items: Dict[str, Dict[str, Any]] = {}
        business_query_map: Dict[str, set[str]] = {}

        for idx, query in enumerate(queries):
            logger.info("[priority %s/%s] searching: %s", idx + 1, len(queries), query)
            try:
                results = await self.map_crawler.search_rehearsal_rooms(query)
                discovered_business_ids: List[str] = []
                missing_id_count = 0
                excluded_non_bookable_count = 0

                for item in results:
                    business_id = item.get("id")
                    booking_business_id = item.get("bookingBusinessId")
                    if not business_id:
                        missing_id_count += 1
                        continue
                    if not booking_business_id or str(booking_business_id) != str(business_id):
                        excluded_non_bookable_count += 1
                        continue
                    business_id = str(business_id)
                    discovered_business_ids.append(business_id)
                    business_query_map.setdefault(business_id, set()).add(query)
                    dedup_items.setdefault(business_id, item)

                query_reports.append(
                    {
                        "query": query,
                        "discovered": len(results),
                        "discovered_with_id": len(discovered_business_ids),
                        "missing_id": missing_id_count,
                        "excluded_non_bookable": excluded_non_bookable_count,
                        "unique_businesses_in_query": len(set(discovered_business_ids)),
                    }
                )
                # 역 쿼리 간 랜덤 지연으로 burst 호출 방지
                await asyncio.sleep(0.8 + random.uniform(0, 0.8))
            except Exception as e:
                logger.error("Priority query failed (%s): %s", query, e)
                query_reports.append(
                    {
                        "query": query,
                        "discovered": 0,
                        "discovered_with_id": 0,
                        "missing_id": 0,
                        "excluded_non_bookable": 0,
                        "unique_businesses_in_query": 0,
                        "query_error": str(e),
                    }
                )

        target_items: List[Dict[str, Any]] = []
        for business_id, item in dedup_items.items():
            enriched = dict(item)
            enriched["source_queries"] = sorted(list(business_query_map.get(business_id, set())))
            target_items.append(enriched)

        total_unique_before_limit = len(target_items)
        if isinstance(max_targets, int) and max_targets > 0:
            target_items = target_items[:max_targets]

        success_count, failed_count, failures, skipped = await self._collect_items(target_items)
        skipped_no_rooms = [row for row in skipped if row.get("status") == "skipped_no_rooms"]
        skipped_non_rehearsal = [row for row in skipped if row.get("status") == "skipped_non_rehearsal"]
        skipped_filtered_rooms = [row for row in skipped if row.get("status") == "skipped_all_rooms_filtered"]

        return {
            "mode": "priority_areas",
            "queries": queries,
            "query_reports": query_reports,
            "total_unique_before_limit": total_unique_before_limit,
            "total_unique": len(target_items),
            "success": success_count,
            "failed": failed_count,
            "failures": failures,
            "skipped": len(skipped),
            "skipped_no_rooms": len(skipped_no_rooms),
            "skipped_non_rehearsal": len(skipped_non_rehearsal),
            "skipped_all_rooms_filtered": len(skipped_filtered_rooms),
            "skipped_details": skipped,
        }

    async def collect_by_query(self, query: str) -> Dict[str, Any]:
        """
        Search and collect rooms.
        Global policy: always constrained to configured priority areas.
        
        Args:
            query: Search keyword (e.g., "Hongdae practice room")
            
        Returns:
            Dict containing:
            - mode: collection mode identifier
            - queries: configured priority-area query list
            - query_reports: per-query discovery summary
            - total_unique_before_limit: deduplicated targets before max_targets
            - total_unique: deduplicated targets after max_targets
            - success: number of collected businesses
            - failed: number of failed businesses
            - failures: per-business failure details
            - skipped: per-business skip details
            - requested_query: original query string (for audit only)
        """
        logger.info(
            "Ignoring direct query '%s' due to global priority-area policy. "
            "Collecting from fixed priority areas instead.",
            query,
        )
        result = await self.collect_priority_areas()
        result["requested_query"] = query
        return result

    async def collect_all_regions(self) -> Dict[str, Any]:
        """
        Collect rooms from globally configured priority areas.
        """
        logger.info("Starting global-priority collection (fixed 6 areas)...")
        return await self.collect_priority_areas()

    async def _collect_items(
        self,
        items: List[Dict[str, Any]],
    ) -> Tuple[int, int, List[Dict[str, Any]], List[Dict[str, Any]]]:
        """각 아이템의 business ID별로 수집하고 성공/실패 통계를 집계한다."""
        success_count = 0
        failed_count = 0
        failures: List[Dict[str, Any]] = []
        skipped: List[Dict[str, Any]] = []
        total_items = len(items)

        for idx, item in enumerate(items):
            try:
                business_id = item.get("id")
                if not business_id:
                    raise ValueError("missing business id in search result")
                logger.info(
                    "Collecting item %s/%s: %s (%s)",
                    idx + 1,
                    total_items,
                    item.get("name", ""),
                    business_id,
                )
                self._source_item_hints[str(business_id)] = item
                result = await self.collect_by_id(str(business_id))
                if isinstance(result, dict):
                    status = str(result.get("status") or "")
                    if status.startswith("skipped_"):
                        skipped.append(
                            {
                                "business_id": item.get("id", ""),
                                "business_name": item.get("name", ""),
                                "source_queries": item.get("source_queries", []),
                                **result,
                            }
                        )
                        continue
                success_count += 1
            except Exception as e:
                logger.exception("Failed to collect item=%s", item)
                failed_count += 1
                failures.append({
                    "business_id": item.get("id", ""),
                    "business_name": item.get("name", ""),
                    "source_queries": item.get("source_queries", []),
                    "reason": str(e),
                })

        return success_count, failed_count, failures, skipped

    async def collect_by_id(self, business_id: str) -> Dict[str, Any]:
        """특정 Business ID의 룸 정보를 수집하고 저장한다."""
        logger.info(f"Collecting business_id: {business_id}")
        source_hint = self._source_item_hints.get(str(business_id))

        # 1. 상세 정보 조회
        data = await self.room_fetcher.fetch_full_info(
            business_id,
            source_hint=source_hint,
        )
        if not data:
            raise ValueError(f"No data found for business {business_id}")

        business = data["business"]
        rooms = data["rooms"]

        # 대표 키워드 수집: place 페이지에서 직접 가져오는 것이 기본 경로.
        # GraphQL API는 키워드를 내려주지 않으므로 source_hint 유무와 관계없이 실행한다.
        has_source_hint = source_hint is not None
        place_id = (
            (source_hint or {}).get("placeId")
            or business.get("placeId")
        )
        has_representative_keywords = source_hint and any(
            source_hint.get(field) for field in self.REPRESENTATIVE_KEYWORD_FIELDS
        )
        if not has_representative_keywords and place_id:
            reveal_keywords = getattr(self.map_crawler, "reveal_representative_keywords", None)
            if callable(reveal_keywords):
                try:
                    revealed = reveal_keywords(str(place_id))
                    if inspect.isawaitable(revealed):
                        revealed = await revealed
                    if isinstance(revealed, list):
                        normalized = [str(v).strip() for v in revealed if isinstance(v, str) and str(v).strip()]
                    else:
                        normalized = []
                    if normalized:
                        enriched = dict(source_hint or {})
                        enriched["representativeKeywords"] = normalized
                        source_hint = enriched
                        self._source_item_hints[str(business_id)] = enriched
                        logger.info(
                            "Fetched representative keywords from place page: business_id=%s place_id=%s",
                            business_id,
                            place_id,
                        )
                except Exception as e:
                    logger.warning(
                        "Representative keyword fetch failed: business_id=%s place_id=%s err=%s",
                        business_id,
                        place_id,
                        e,
                    )

        domain_decision = self._evaluate_rehearsal_domain(
            source_hint=source_hint,
            business=business,
            rooms=rooms,
        )

        # 도메인 필터는 지도 검색으로 유입된 항목(source_hint 존재)에만 강제 적용한다.
        # 수동 점검 목적의 direct collect_by_id 호출은 최대한 허용적으로 유지한다.
        if has_source_hint and not domain_decision["is_candidate"]:
            logger.warning(
                "Skipping non-rehearsal business %s (pos=%s, neg=%s)",
                business_id,
                domain_decision["positive_hits"],
                domain_decision["negative_hits"],
            )
            return {
                "status": "skipped_non_rehearsal",
                "reason": domain_decision["reason"],
                "positive_hits": domain_decision["positive_hits"],
                "negative_hits": domain_decision["negative_hits"],
                "representative_keywords": domain_decision["representative_keywords"],
            }

        if not rooms:
            logger.warning(
                "No room inventory for business %s. Skipping collection (contact-required candidate).",
                business_id,
            )
            return {
                "status": "skipped_no_rooms",
                "reason": "biz_items_empty",
                "is_rehearsal_candidate": domain_decision["is_candidate"],
                "positive_hits": domain_decision["positive_hits"],
                "negative_hits": domain_decision["negative_hits"],
                "representative_keywords": domain_decision["representative_keywords"],
            }

        target_rooms, filtered_stats = self._filter_rooms_for_regex_parsing(rooms)
        if not target_rooms:
            if (
                filtered_stats["non_rehearsal_keyword"] > 0
                and filtered_stats["missing_reservation"] == 0
            ):
                skip_reason = "rooms_filtered_non_rehearsal_keywords"
            elif (
                filtered_stats["missing_reservation"] > 0
                and filtered_stats["non_rehearsal_keyword"] == 0
            ):
                skip_reason = "rooms_missing_reservation_metadata"
            else:
                skip_reason = "rooms_filtered_mixed_rules"
            logger.warning(
                "All rooms filtered out for business %s (inquiry_required=%s, missing_reservation=%s, non_rehearsal_keyword=%s).",
                business_id,
                filtered_stats["inquiry_required"],
                filtered_stats["missing_reservation"],
                filtered_stats["non_rehearsal_keyword"],
            )
            return {
                "status": "skipped_all_rooms_filtered",
                "reason": skip_reason,
                "inquiry_required": filtered_stats["inquiry_required"],
                "missing_reservation": filtered_stats["missing_reservation"],
                "non_rehearsal_keyword": filtered_stats["non_rehearsal_keyword"],
                "is_rehearsal_candidate": domain_decision["is_candidate"],
                "positive_hits": domain_decision["positive_hits"],
                "negative_hits": domain_decision["negative_hits"],
                "representative_keywords": domain_decision["representative_keywords"],
            }

        if (
            filtered_stats["inquiry_required"]
            or filtered_stats["missing_reservation"]
            or filtered_stats["non_rehearsal_keyword"]
        ):
            logger.info(
                "Room selection summary for business %s: inquiry_required=%s (included), missing_reservation=%s (excluded), non_rehearsal_keyword=%s (excluded), remaining=%s/%s",
                business_id,
                filtered_stats["inquiry_required"],
                filtered_stats["missing_reservation"],
                filtered_stats["non_rehearsal_keyword"],
                len(target_rooms),
                len(rooms),
            )

        # 2. 규칙 기반 파싱 (배치 + 동시성)
        # 다운스트림 호환을 위해 business 수준 컨텍스트를 페이로드에 유지
        business_desc = (business.get("desc") or "")[: self.MAX_BUSINESS_DESC_CHARS]
        parse_items = []
        for room in target_rooms:
            parse_items.append({
                "id": room["bizItemId"],
                "name": room["name"],
                "desc": room.get("desc") or "",
                "business_desc": business_desc
            })
        
        # 병렬 처리를 위한 청크 분할
        parsed_results = await self._parse_with_concurrency(parse_items)

        # 3. DB 저장 (Branch -> Room(이미지 포함))
        saved = await self._save_to_db(business, target_rooms, parsed_results, source_hint=source_hint)
        if not saved:
            logger.warning(
                "Skipped DB save for requested business_id=%s due to missing business_id in fetched payload",
                business_id,
            )
            return {
                "status": "skipped_missing_business_id",
                "reason": "missing_business_id",
                "is_rehearsal_candidate": domain_decision["is_candidate"],
                "representative_keywords": domain_decision["representative_keywords"],
            }
        logger.info(f"Successfully saved business {business_id} with {len(target_rooms)} rooms")

        # 4. 미해결 항목 내보내기 (수동 검증 큐)
        await self._export_unresolved(business, target_rooms, parsed_results)
        return {
            "status": "collected",
            "rooms_collected": len(target_rooms),
            "is_rehearsal_candidate": domain_decision["is_candidate"],
            "representative_keywords": domain_decision["representative_keywords"],
        }

    async def _parse_with_concurrency(self, items: List[Dict]) -> Dict[str, Dict]:
        """아이템을 동시성 배치로 파싱한다."""
        if not items:
            return {}
            
        # 아이템 청크 분할
        chunks = [items[i:i + self.BATCH_SIZE] for i in range(0, len(items), self.BATCH_SIZE)]
        logger.info(f"Splitting {len(items)} items into {len(chunks)} chunks (batch size: {self.BATCH_SIZE})")
        
        # 동시 실행 제한 세마포어
        semaphore = asyncio.Semaphore(self.MAX_CONCURRENT_BATCHES)
        
        async def parse_chunk(chunk: List[Dict]) -> Dict[str, Dict]:
            async with semaphore:
                return await self.parser_service.parse_room_desc_batch(chunk)
        
        # 모든 청크를 동시 실행(세마포어로 제한)
        results = await asyncio.gather(*[parse_chunk(c) for c in chunks])
        
        # 결과 병합
        merged = {}
        for r in results:
            merged.update(r)
        return merged

    @classmethod
    def _iter_text_values(cls, payload: Any, depth: int = 0, max_depth: int = 3) -> List[str]:
        """키워드 판별을 위해 중첩 payload에서 텍스트 값을 추출한다."""
        if payload is None or depth > max_depth:
            return []
        if isinstance(payload, str):
            stripped = payload.strip()
            return [stripped] if stripped else []
        if isinstance(payload, (int, float, bool)):
            return [str(payload)]
        if isinstance(payload, list):
            values: List[str] = []
            for item in payload:
                values.extend(cls._iter_text_values(item, depth + 1, max_depth))
            return values
        if isinstance(payload, dict):
            values = []
            for key, value in payload.items():
                key_text = str(key).strip()
                if key_text:
                    values.append(key_text)
                values.extend(cls._iter_text_values(value, depth + 1, max_depth))
            return values
        return []

    @classmethod
    def _collect_representative_keywords(
        cls,
        source_hint: Optional[Dict[str, Any]],
        business: Dict[str, Any],
    ) -> List[str]:
        """대표 키워드 계열 필드에서 텍스트 후보를 수집한다."""
        texts: List[str] = []

        for payload in (source_hint, business):
            if not isinstance(payload, dict):
                continue
            for field in cls.REPRESENTATIVE_KEYWORD_FIELDS:
                if field in payload:
                    texts.extend(cls._iter_text_values(payload.get(field)))

        normalized = [t.lower() for t in texts if isinstance(t, str) and t.strip()]
        return sorted(set(normalized))

    @classmethod
    def _extract_representative_keywords(cls, keywords: List[str]) -> List[str]:
        """대표 키워드 텍스트 중 합주실 판별 키워드를 추출한다."""
        if not keywords:
            return []

        hits: set[str] = set()
        for keyword in keywords:
            for rule in cls.REHEARSAL_KEYWORDS:
                if rule in keyword:
                    hits.add(rule)
        return sorted(hits)

    @classmethod
    def _evaluate_rehearsal_domain(
        cls,
        source_hint: Optional[Dict[str, Any]],
        business: Dict[str, Any],
        rooms: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        representative_candidates = cls._collect_representative_keywords(
            source_hint=source_hint,
            business=business,
        )
        representative_hits = cls._extract_representative_keywords(representative_candidates)

        raw_name = (
            (source_hint or {}).get("name")
            or business.get("businessDisplayName")
            or business.get("name")
            or ""
        )
        # 이름 + 소개(desc/description) + 예약안내(bookingGuideJson)에서 키워드 검색
        text_sources = [str(raw_name)]
        for payload in (source_hint, business):
            if not isinstance(payload, dict):
                continue
            for field in ("description", "desc"):
                value = payload.get(field)
                if isinstance(value, str) and value.strip():
                    text_sources.append(value)
        guide = business.get("bookingGuideJson")
        if isinstance(guide, list):
            for entry in guide:
                words = (entry or {}).get("words", "") if isinstance(entry, dict) else ""
                if isinstance(words, str) and words.strip():
                    text_sources.append(words)
        elif isinstance(guide, str) and guide.strip():
            text_sources.append(guide)
        combined_text = " ".join(text_sources).lower()
        name_hits = sorted({kw for kw in cls.REHEARSAL_KEYWORDS if kw in combined_text})

        positive_hits = sorted(set(representative_hits + name_hits))

        # 룸 이름에서도 키워드 탐색 (위 단계에서 미발견 시)
        if not positive_hits and rooms:
            for room in rooms:
                room_name = str(room.get("name") or "").lower()
                matched = {kw for kw in cls.REHEARSAL_KEYWORDS if kw in room_name}
                if matched:
                    positive_hits.extend(list(matched))
            positive_hits = sorted(set(positive_hits))

        is_candidate = bool(positive_hits)
        reason = "matched_representative_or_name_keywords" if is_candidate else "no_rehearsal_keyword_match"

        return {
            "is_candidate": is_candidate,
            "reason": reason,
            "positive_hits": positive_hits,
            "negative_hits": [],
            "representative_keywords": representative_candidates,
        }


    @classmethod
    def _build_room_name_tokens(cls, rooms: List[Dict[str, Any]]) -> set[str]:
        tokens = {
            normalize_name_token((room or {}).get("name"))
            for room in rooms
            if isinstance(room, dict)
        }
        tokens.discard("")
        return tokens

    @staticmethod
    def _clean_branch_name(name: str) -> str:
        """지점명에서 프로모션/운영 안내 문구를 제거한다."""
        clean = re.sub(r"\s+", " ", (name or "")).strip()
        if not clean:
            return clean

        # 대괄호 프로모션/운영 태그 제거
        promo_markers = (
            "특가", "할인", "이벤트", "event", "예약", "문의",
            "전화", "방문", "상담", "운영", "공지",
        )
        while True:
            m = re.match(r"^\s*\[([^\]]{1,60})\]\s*", clean)
            if not m:
                break
            tag = m.group(1).strip().lower()
            if any(marker in tag for marker in promo_markers):
                clean = clean[m.end():].strip()
                continue
            break

        # 요일/예약 운영 꼬리 제거: "월-목 / 금토일 예약", "방문 상담" 등
        clean = re.sub(
            r"\s*[/·,]\s*(?:[월화수목금토일]\s*[-~]\s*)*[월화수목금토일공휴일\s]*(?:예약|운영|문의|상담)?\s*$",
            "", clean,
        )
        clean = re.sub(r"\s+(?:예약|방문\s*상담|전화\s*문의)\s*$", "", clean)

        return re.sub(r"\s+", " ", clean).strip()

    @staticmethod
    def _is_placeholder_branch_name(candidate: str, business_id: str) -> bool:
        lowered = candidate.strip().lower()
        return lowered in {str(business_id).lower(), f"business-{str(business_id).lower()}"}

    @classmethod
    def _is_room_name_collision(cls, candidate: str, room_name_tokens: set[str]) -> bool:
        token = normalize_name_token(candidate)
        return bool(token) and token in room_name_tokens

    @staticmethod
    def _is_missing_display_name_column_error(error: Exception) -> bool:
        message = str(error).lower()
        return "display_name" in message and (
            "42703" in message or "column" in message or "schema cache" in message
        )

    def _fetch_existing_branch_name_candidates(self, business_id: str) -> List[str]:
        if not business_id:
            return []
        try:
            response = (
                self.supabase.table("branch")
                .select("name,display_name")
                .eq("business_id", business_id)
                .execute()
            )
        except Exception as e:
            if self._is_missing_display_name_column_error(e):
                logger.info(
                    "branch.display_name column unavailable; falling back to name-only fetch: business_id=%s",
                    business_id,
                )
                try:
                    response = (
                        self.supabase.table("branch")
                        .select("name")
                        .eq("business_id", business_id)
                        .execute()
                    )
                except Exception as fallback_error:
                    logger.warning(
                        "Failed to fetch existing branch name for collision guard: business_id=%s err=%s",
                        business_id,
                        fallback_error,
                    )
                    return []
            else:
                logger.warning(
                    "Failed to fetch existing branch name for collision guard: business_id=%s err=%s",
                    business_id,
                    e,
                )
                return []

        rows = getattr(response, "data", None)
        if not isinstance(rows, list) or not rows:
            return []

        row = rows[0]
        if not isinstance(row, dict):
            return []
        return [row.get("name"), row.get("display_name")]

    @classmethod
    def _resolve_branch_display_name(
        cls,
        *,
        business_id: str,
        business: Dict[str, Any],
        source_hint: Optional[Dict[str, Any]],
        rooms: List[Dict[str, Any]],
        existing_candidates: List[str],
    ) -> str:
        room_name_tokens = cls._build_room_name_tokens(rooms)
        candidates: List[Tuple[str, Any]] = [
            ("source_hint.name", (source_hint or {}).get("name")),
            ("business.businessDisplayName", business.get("businessDisplayName")),
            ("business.name", business.get("name")),
            ("existing.name", existing_candidates[0] if len(existing_candidates) > 0 else None),
            ("existing.display_name", existing_candidates[1] if len(existing_candidates) > 1 else None),
        ]

        for source, raw_candidate in candidates:
            if not isinstance(raw_candidate, str):
                continue
            candidate = re.sub(r"\s+", " ", raw_candidate).strip()
            if not candidate:
                continue
            cleaned = cls._clean_branch_name(candidate)
            if not cleaned:
                continue
            if cls._is_placeholder_branch_name(cleaned, business_id):
                continue
            if cls._is_room_name_collision(cleaned, room_name_tokens):
                logger.warning(
                    "Rejected branch name candidate due to room-name collision: business_id=%s source=%s candidate=%s",
                    business_id,
                    source,
                    cleaned,
                )
                continue
            return cleaned

        return business_id

    async def _save_to_db(
        self,
        business: Dict,
        rooms: List[Dict],
        parsed_results: Dict,
        source_hint: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """수집/파싱된 데이터를 Supabase에 저장한다."""
        
        # 1. Save Branch
        business_id = str(business.get("businessId") or business.get("id") or "").strip()
        if not business_id:
            logger.warning("Skipping DB save: Received empty business_id for business data=%s", business)
            return False

        coords = business.get("coordinates")
        existing_name_candidates = self._fetch_existing_branch_name_candidates(business_id)
        display_name = self._resolve_branch_display_name(
            business_id=business_id,
            business=business,
            source_hint=source_hint,
            rooms=rooms,
            existing_candidates=existing_name_candidates,
        )
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
                        logger.info(
                            "Recovered phone via place click fallback: business_id=%s place_id=%s",
                            business.get("businessId"),
                            place_id,
                        )
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

        # display_name 정제: 예약 안내 문구, 대괄호 태그 제거
        clean_display_name = self._sanitize_display_name(display_name)

        branch_data = {
            "business_id": business_id,
            "name": display_name,
            "display_name": clean_display_name,
        }

        # business 페이로드 누락 시 기존 좌표를 null로 덮어쓰지 않는다.
        lat_val: Optional[float] = None
        lng_val: Optional[float] = None
        if isinstance(coords, dict):
            lat_val = self._coerce_float(coords.get("latitude"))
            lng_val = self._coerce_float(coords.get("longitude"))
        elif isinstance(coords, list) and len(coords) >= 2:
            lng_val = self._coerce_float(coords[0])
            lat_val = self._coerce_float(coords[1])

        # 위경도 뒤바뀜 보정: 한국 좌표 기준 lat < 100, lng > 100
        if lat_val is not None and lng_val is not None and lat_val > 100 and lng_val < 100:
            lat_val, lng_val = lng_val, lat_val

        if lat_val is not None:
            branch_data["lat"] = lat_val
        if lng_val is not None:
            branch_data["lng"] = lng_val
        if branch_standby_days is not None:
            branch_data["standby_days"] = branch_standby_days
        if branch_phone_number:
            branch_data["phone_number"] = branch_phone_number
        
        # Branch도 room과 동일하게 롤링 배포 중 스키마 차이를 허용한다.
        self._upsert_branch_with_schema_fallback(branch_data)

        # [데이터 보존] 수동 오버라이드 확인을 위해 해당 business의 기존 room 조회
        try:
            existing_resp = self.supabase.table("room").select("*").eq("business_id", business_id).execute()
            existing_map = {r["biz_item_id"]: r for r in existing_resp.data}
        except Exception as e:
            logger.warning(f"Failed to fetch existing rooms: {e}")
            existing_map = {}

        # 2. 룸 저장 (이미지 포함)
        for room in rooms:
            rid = room["bizItemId"]
            parsed = parsed_results.get(rid, {})
            existing = existing_map.get(rid)

            # 이미지 URL 추출
            images = room.get("bizItemResources", [])
            image_urls = [img["resourceUrl"] for img in images] if images else []

            # 신규 값 (MANUAL_REVIEW_FLAG = 100, 파싱 실패 시 수동 검토용)
            # 수용 인원 결정 우선순위:
            #   1) 룸 이름/설명의 고신뢰 텍스트 패턴
            #   2) 파서 출력
            #   3) 수동 검토 플래그
            text_max_cap, text_rec_cap, text_rec_range = self._extract_capacity_text_signals(room)

            new_max_cap = text_max_cap if text_max_cap is not None else parsed.get("max_capacity")
            if new_max_cap is None:
                new_max_cap = self.MANUAL_REVIEW_FLAG
                
            # HACK: [이슈 6 기술부채] recommend_capacity(단일값) 레거시.
            # DTO에서는 제거됐으나 DB 컬럼과 _calculate_capacity_range 의존성 때문에 upsert 유지.
            # 향후 recommend_capacity_range로 완전히 대체 시 이 컬럼 제거 예정.
            new_rec_cap = text_rec_cap if text_rec_cap is not None else parsed.get("recommend_capacity")
            if new_rec_cap is None and new_max_cap != self.MANUAL_REVIEW_FLAG:
                new_rec_cap = new_max_cap // 2 if new_max_cap > 4 else new_max_cap
            if new_rec_cap is None:
                new_rec_cap = self.MANUAL_REVIEW_FLAG
                
            new_price = self._extract_price(room)
            price_inferred = self._infer_capacity_from_price(
                business_id=business_id,
                room_name=room.get("name"),
                price_per_hour=new_price,
            )
            new_price_config = parsed.get("price_config")

            # [로직] 새 값이 기본값(0 또는 1)이면 기존 유효 값을 보존
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

                # 새 가격이 0/None이고 기존 값이 유효하면 기존 값 보존
                # NOTE: self._extract_price는 값이 없으면 None을 반환하며, None은 > 0이 아님.
                existing_price = existing.get("price_per_hour")
                if (not new_price or new_price == 0) and existing_price and existing_price > 0:
                    final_price = existing_price

            price_inferred_applied = False
            if final_max_cap == self.MANUAL_REVIEW_FLAG and price_inferred:
                final_max_cap = price_inferred["max_capacity"]
                price_inferred_applied = True
            if final_rec_cap == self.MANUAL_REVIEW_FLAG and price_inferred:
                final_rec_cap = price_inferred["recommend_capacity"]
                price_inferred_applied = True

            # price_inferred의 recommend_range는 max_cap과 rec_cap이 모두
            # 동일 price band에서 추론된 경우에만 사용 (혼합 소스 불일치 방지)
            inferred_range = None
            if (
                price_inferred
                and price_inferred_applied
                and final_max_cap == price_inferred.get("max_capacity")
                and final_rec_cap == price_inferred.get("recommend_capacity")
            ):
                inferred_range = price_inferred.get("recommend_range")

            # 파서가 명시적으로 대체 값을 제공하지 않으면 기존 JSON 값을 보존
            existing_price_config = existing.get("price_config", []) if existing else []
            existing_base_cap = existing.get("base_capacity") if existing else None
            existing_extra_charge = existing.get("extra_charge") if existing else None
            structured_extra_charge = self._extract_structured_extra_charge(room)

            final_price_config = parsed["price_config"] if "price_config" in parsed else existing_price_config
            if not final_price_config and existing_price_config:
                final_price_config = existing_price_config
            final_base_cap = parsed["base_capacity"] if "base_capacity" in parsed else existing_base_cap
            if structured_extra_charge is not None:
                final_extra_charge = structured_extra_charge
            elif parsed.get("extra_charge") is not None:
                final_extra_charge = parsed["extra_charge"]
            else:
                final_extra_charge = existing_extra_charge

            # Boolean 필드 fallback
            existing_can_reserve = existing.get("can_reserve_one_hour", True) if existing else True
            parsed_can_reserve = parsed.get("can_reserve_one_hour")
            structured_can_reserve = self._extract_structured_can_reserve_one_hour(room)
            if structured_can_reserve is not None:
                final_can_reserve = structured_can_reserve
            elif parsed_can_reserve is not None:
                final_can_reserve = parsed_can_reserve
            else:
                final_can_reserve = existing_can_reserve
            
            existing_requires_call = False
            if existing:
                existing_requires_call = existing.get("requires_contact_on_sameday")
                if existing_requires_call is None:
                    existing_requires_call = existing.get("requires_contact_same_day")
                if existing_requires_call is None:
                    existing_requires_call = existing.get("requires_call_on_sameday", False)

            parsed_requires_call = parsed.get("requires_contact_on_sameday")
            if parsed_requires_call is None:
                parsed_requires_call = parsed.get("requires_same_day_contact")
            if parsed_requires_call is None:
                parsed_requires_call = parsed.get("requires_contact_same_day")
            if parsed_requires_call is None:
                parsed_requires_call = parsed.get("requires_call_on_same_day")

            structured_requires_call = self._extract_structured_requires_call_on_same_day(room)
            if structured_requires_call is not None:
                final_requires_call = structured_requires_call
            elif parsed_requires_call is not None:
                final_requires_call = parsed_requires_call
            else:
                final_requires_call = existing_requires_call

            # 룸 데이터 구성
            final_max_cap_int = self._coerce_int(final_max_cap)
            if final_max_cap_int is None:
                final_max_cap_int = self.MANUAL_REVIEW_FLAG

            final_rec_cap_int = self._coerce_int(final_rec_cap)
            if final_rec_cap_int is None:
                final_rec_cap_int = (
                    final_max_cap_int // 2 if final_max_cap_int != self.MANUAL_REVIEW_FLAG else self.MANUAL_REVIEW_FLAG
                )

            # DB 제약조건 보정: recommend_capacity <= max_capacity
            if (
                final_rec_cap_int != self.MANUAL_REVIEW_FLAG
                and final_max_cap_int != self.MANUAL_REVIEW_FLAG
                and final_rec_cap_int > final_max_cap_int
            ):
                final_rec_cap_int = final_max_cap_int

            final_base_cap_int = self._coerce_int(final_base_cap)
            final_extra_charge_int = self._coerce_int(final_extra_charge)
            final_price_int = self._coerce_int(final_price)
            if final_price_int is None or final_price_int < 0:
                final_price_int = 0

            # price=0 룸은 유효한 예약 정보를 제공할 수 없으므로 저장하지 않는다.
            if final_price_int == 0:
                logger.info(
                    "Skipping room with price=0: business_id=%s biz_item_id=%s name=%s",
                    business_id, rid, room.get("name"),
                )
                continue

            room_data = {
                "business_id": business_id,
                "biz_item_id": rid,
                "name": parsed.get("clean_name") or room["name"],
                "price_per_hour": final_price_int,
                # 스키마 제약: null이면 기본값 1
                "max_capacity": final_max_cap_int,
                "recommend_capacity": final_rec_cap_int,
                # [v2.0.0] 신규 필드: 권장 인원 범위 및 동적 가격 정책
                "recommend_capacity_range": self._calculate_capacity_range(
                    text_rec_range
                    or parsed.get("recommend_capacity_range")
                    or inferred_range,
                    final_rec_cap_int,
                    final_max_cap_int,
                    final_base_cap_int,
                    final_extra_charge_int
                ),
                "price_config": final_price_config,
                "base_capacity": final_base_cap_int,
                "extra_charge": final_extra_charge_int,
                # NOTE: upsert 키는 실제 DB 컬럼명과 반드시 일치해야 함. AliasChoices는 SELECT에만 효과 있음.
                "requires_contact_on_sameday": final_requires_call,
                "requires_contact_same_day": final_requires_call, # TODO: schema migration 완료 후 old column 제거
                "can_reserve_one_hour": final_can_reserve,
                "image_urls": image_urls  # JSONB 컬럼에 저장
            }
            
            # 룸 Upsert (롤링 마이그레이션용 스키마 호환 fallback 포함)
            self._upsert_room_with_schema_fallback(room_data)

        return True

    def _infer_capacity_from_price(
        self,
        business_id: Optional[str],
        room_name: Optional[str],
        price_per_hour: Optional[int],
    ) -> Optional[Dict[str, Any]]:
        """업체별 가격 규칙을 사용하여 수용 인원을 추론한다."""
        if not business_id or not isinstance(price_per_hour, int) or price_per_hour <= 0:
            return None

        rules = self.PRICE_CAPACITY_RULES.get(str(business_id))
        if rules:
            best_rule: Optional[Dict[str, Any]] = None
            best_gap: Optional[int] = None

            for rule in rules:
                rule_price = rule.get("price")
                if not isinstance(rule_price, int):
                    continue
                gap = abs(rule_price - price_per_hour)
                if gap > self.PRICE_MATCH_TOLERANCE:
                    continue
                if best_gap is None or gap < best_gap:
                    best_gap = gap
                    best_rule = rule

            if best_rule:
                logger.info(
                    "Price-based capacity inference applied: business_id=%s room=%s price=%s rule_price=%s max=%s",
                    business_id,
                    room_name or "",
                    price_per_hour,
                    best_rule.get("price"),
                    best_rule.get("max_capacity"),
                )
                return {
                    "max_capacity": best_rule.get("max_capacity"),
                    "recommend_capacity": best_rule.get("recommend_capacity"),
                    "recommend_range": best_rule.get("recommend_range"),
                }

        # 업체별 규칙 미매칭 시 가격대 기반 글로벌 fallback
        for band_rule in self.PRICE_BAND_CAPACITY_DEFAULTS:
            band_name = band_rule.get("name")
            min_price = band_rule.get("min_price")
            max_price = band_rule.get("max_price")
            default_max = band_rule.get("max_capacity")
            default_rec = band_rule.get("recommend_capacity")

            if not isinstance(min_price, int) or not isinstance(default_max, int):
                continue
            if max_price is not None and not isinstance(max_price, int):
                continue
            if price_per_hour < min_price:
                continue
            if max_price is not None and price_per_hour > max_price:
                continue

            if not isinstance(default_rec, int):
                default_rec = default_max // 2 if default_max > 4 else default_max

            # ±delta 규칙으로 범위 동적 계산 (rec < 9: ±1, rec >= 9: ±2)
            delta = 2 if default_rec >= 9 else 1
            rec_range = [max(default_rec - delta, 1), min(default_rec + delta, default_max)]

            rec_cap = default_rec

            logger.info(
                "Price-band fallback inference applied: business_id=%s room=%s price=%s band=%s max=%s",
                business_id,
                room_name or "",
                price_per_hour,
                band_name,
                default_max,
            )
            return {
                "max_capacity": default_max,
                "recommend_capacity": rec_cap,
                "recommend_range": rec_range,
            }

        return None

    def _upsert_room_with_schema_fallback(self, room_data: Dict[str, Any]) -> None:
        """룸 행을 upsert하고, 알 수 없는 컬럼이 포함되면 재시도한다.

        롤링 마이그레이션 중 일부 환경에서 alias 컬럼(requires_contact_on_sameday vs
        requires_contact_same_day 등)이 아직 없을 수 있다.
        """
        payload = dict(room_data)
        for col in list(self._unsupported_room_columns):
            payload.pop(col, None)

        for _ in range(6):
            try:
                self.supabase.table("room").upsert(payload).execute()
                return
            except Exception as exc:
                missing_col = self._extract_missing_column_from_error(exc)
                if not missing_col or missing_col not in payload:
                    raise
                logger.warning(
                    "Room upsert fallback: removing missing column '%s' and retrying",
                    missing_col,
                )
                self._unsupported_room_columns.add(missing_col)
                payload.pop(missing_col, None)

        # 방어 코드 (정상적으로는 위 루프에서 return 됨)
        self.supabase.table("room").upsert(payload).execute()

    # 왜: 롤링 배포 중 브랜치 컬럼 스키마가 환경마다 달라도 수집 파이프라인을 중단시키지 않기 위해 필요하다.
    # 사용처: _save_to_db에서 branch upsert 직전에 호출되며, 입력 branch_data(dict)를 fallback 처리해 저장한다.
    def _upsert_branch_with_schema_fallback(self, branch_data: Dict[str, Any]) -> None:
        """
        왜: 롤링 배포 중 브랜치 컬럼 스키마가 환경마다 달라질 수 있어 수집 파이프라인이 중단되지 않게 한다.
        사용처: _save_to_db에서 branch upsert 직전에 호출되며, 입력은 branch_data(dict), 출력은 DB upsert 완료(예외 시 상위 전파)다.
        """
        payload = dict(branch_data)
        for col in list(self._unsupported_branch_columns):
            payload.pop(col, None)

        for _ in range(6):
            try:
                self.supabase.table("branch").upsert(payload).execute()
                return
            except Exception as exc:
                missing_col = self._extract_missing_column_from_error(exc)
                if not missing_col or missing_col not in payload:
                    raise
                logger.warning(
                    "Branch upsert fallback: removing missing column '%s' and retrying",
                    missing_col,
                )
                self._unsupported_branch_columns.add(missing_col)
                payload.pop(missing_col, None)

        # 방어 코드: 정상적으로는 위 루프에서 return 된다.
        self.supabase.table("branch").upsert(payload).execute()

    @staticmethod
    def _extract_missing_column_from_error(exc: Exception) -> Optional[str]:
        """PostgREST/Supabase 에러 텍스트에서 누락된 컬럼명을 추출한다."""
        text = str(exc)

        patterns = [
            r"Could not find the '([^']+)' column",
            r'column "([^"]+)" does not exist',
        ]
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                return match.group(1)
        return None

    def _extract_structured_can_reserve_one_hour(self, room: Dict) -> Optional[bool]:
        """구조화된 예약 정책 필드에서 1시간 예약 가능 여부를 추론한다."""
        unit_code = (room.get("bookingTimeUnitCode") or "").upper()
        min_booking_time = room.get("minBookingTime")

        if isinstance(min_booking_time, (int, float)):
            if "MIN" in unit_code:
                return min_booking_time <= 60
            return min_booking_time <= 1

        booking_count_setting = room.get("bookingCountSettingJson")
        if isinstance(booking_count_setting, str):
            try:
                booking_count_setting = json.loads(booking_count_setting)
            except json.JSONDecodeError:
                booking_count_setting = None

        if isinstance(booking_count_setting, dict):
            for key in ("minBookingTime", "minimumBookingTime", "minTime", "minimumTime"):
                value = booking_count_setting.get(key)
                coerced_value = self._coerce_int(value)
                if coerced_value is not None:
                    if "MIN" in unit_code:
                        return coerced_value <= 60
                    return coerced_value <= 1

        return None

    def _extract_structured_extra_charge(self, room: Dict) -> Optional[int]:
        """텍스트 fallback 전에 구조화된 JSON 필드에서 추가 요금을 추출한다."""
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
        """숫자형 값을 int로 변환한다 (best-effort)."""
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

    @staticmethod
    def _coerce_bool(value: Any) -> Optional[bool]:
        """bool형 값을 bool로 변환한다 (best-effort)."""
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            if value == 0:
                return False
            if value == 1:
                return True
            return None
        if isinstance(value, str):
            lowered = value.strip().lower()
            true_tokens = {"true", "yes", "y", "1", "required", "need", "필수", "필요", "가능"}
            false_tokens = {"false", "no", "n", "0", "optional", "불필요", "불가", "없음"}
            if lowered in true_tokens:
                return True
            if lowered in false_tokens:
                return False
        return None

    @staticmethod
    def _coerce_float(value: Any) -> Optional[float]:
        """숫자형 값을 float로 변환한다 (best-effort)."""
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
    def _extract_phone_number_from_payload(cls, payload: Any) -> Optional[str]:
        """JSON 형태의 페이로드에서 전화번호를 재귀적으로 추출한다."""
        if payload is None:
            return None

        if isinstance(payload, str):
            stripped = payload.strip()
            if not stripped:
                return None
            try:
                parsed = json.loads(stripped)
            except json.JSONDecodeError:
                # 자유 형식 텍스트에서 URL 노이즈를 제거 후 재파싱
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

            ignored_key_tokens = (
                "url",
                "image",
                "img",
                "photo",
                "thumbnail",
                "resource",
                "icon",
                "logo",
            )
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
        """일반 텍스트에서 한국식 사업장 전화번호 토큰을 추출한다."""
        if not text:
            return None

        # 타임스탬프/URL 오탐 방지를 위해 허용 패턴을 엄격하게 유지
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

            # 비전화 숫자 노이즈 방지를 위해 연락처 키워드 근처 토큰 우선
            left = max(0, match.start() - 24)
            right = min(len(text), match.end() + 24)
            window = text[left:right].lower()
            score = 1
            if re.search(r"(전화|문의|연락|콜|tel|phone|contact|call)", window):
                score += 10
            # 0507 안심번호는 사업장 대표번호일 가능성이 높으므로 최우선
            if digits.startswith("0507"):
                score += 20
            elif digits.startswith(("010", "011", "016", "017", "018", "019", "02")):
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
        """비즈니스 페이로드, 지도 힌트, 룸 페이로드에서 지점 전화번호를 추출한다."""
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

    def _extract_capacity_text_signals(
        self, room: Dict[str, Any]
    ) -> Tuple[Optional[int], Optional[int], Optional[List[int]]]:
        """룸 이름/설명 텍스트에서 고신뢰 수용 인원 신호를 추출한다.

        Returns:
            (max_capacity, recommend_capacity, recommend_capacity_range)
        """
        name = room.get("name") or ""
        desc = room.get("desc") or ""
        text = f"{name} {desc}"

        # 최강 패턴: "정원 N명, 최대 M명"
        pair_match = re.search(r"정원\s*(\d+)\s*명[^0-9]{0,20}최대\s*(\d+)\s*명", text)
        if pair_match:
            rec = int(pair_match.group(1))
            max_cap = int(pair_match.group(2))
            return max_cap, rec, [rec, rec]

        rec_cap: Optional[int] = None
        max_cap: Optional[int] = None
        rec_range: Optional[List[int]] = None

        # 권장 범위 패턴: "4~6명", "4-6명", "권장 4~6명"
        range_match = re.search(r"(\d+)\s*[~\-]\s*(\d+)\s*명", text)
        if range_match:
            min_r = int(range_match.group(1))
            max_r = int(range_match.group(2))
            if min_r <= max_r:
                rec_range = [min_r, max_r]
                rec_cap = (min_r + max_r) // 2

        rec_match = re.search(r"정원\s*(\d+)\s*명", text)
        if rec_match:
            rec_cap = int(rec_match.group(1))
            if rec_range is None:
                rec_range = [rec_cap, rec_cap]

        max_match = re.search(r"최대\s*(\d+)\s*명", text)
        if max_match:
            max_cap = int(max_match.group(1))

        return max_cap, rec_cap, rec_range

    def _filter_rooms_for_regex_parsing(self, rooms: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], Dict[str, int]]:
        """비합주실 라벨 및 예약 메타데이터가 없는 룸을 제외한다.

        문의 필요 룸은 전화/채팅/수동 확인 플로우로 예약 가능하므로 포함한다.
        """
        selected: List[Dict[str, Any]] = []
        filtered_stats = {
            "inquiry_required": 0,
            "missing_reservation": 0,
            "non_rehearsal_keyword": 0,
        }

        for room in rooms:
            if self._is_non_rehearsal_room_name(room):
                filtered_stats["non_rehearsal_keyword"] += 1
                continue
            if self._requires_inquiry(room):
                filtered_stats["inquiry_required"] += 1
            if not self._has_reservation_metadata(room):
                filtered_stats["missing_reservation"] += 1
                continue
            selected.append(room)

        return selected, filtered_stats

    def _is_non_rehearsal_room_name(self, room: Dict[str, Any]) -> bool:
        """룸 이름에서 레슨/녹음 등 비합주 라벨 및 안내성 더미 항목을 감지한다."""
        name = room.get("name")
        if not isinstance(name, str) or not name.strip():
            return False
        normalized = name.lower()
        # 안내성 더미 항목: 실제 룸이 아닌 예약 안내/이벤트/견적
        if any(keyword in normalized for keyword in self.NON_ROOM_NAME_KEYWORDS):
            return True
        # 강제 제외 키워드: 다른 장르/용도 → 무조건 필터링
        if any(keyword in normalized for keyword in self.NON_REHEARSAL_ROOM_NAME_KEYWORDS):
            return True
        # 조건부 허용 키워드: 음악 후반작업 → 합주 키워드 공존 시 보존
        if any(keyword in normalized for keyword in self.NON_REHEARSAL_SOFT_KEYWORDS):
            has_positive = any(keyword in normalized for keyword in self.REHEARSAL_KEYWORDS)
            return not has_positive
        return False

    def _requires_inquiry(self, room: Dict[str, Any]) -> bool:
        """구조화/텍스트 정책 블록에서 문의 필요 룸을 감지한다."""
        structured_requires_call = self._extract_structured_requires_call_on_same_day(room)
        if structured_requires_call is True:
            return True
        if structured_requires_call is False:
            return False

        joined_text = " ".join(self._collect_room_policy_texts(room))
        if not joined_text:
            return False

        normalized = joined_text.lower()
        negative_patterns = (
            r"(문의|상담|전화)\s*(없이|불필요)",
            r"(no|not)\s+(need|required).*(call|contact|inquiry)",
            r"(call|contact|inquiry)\s*(is\s*)?(not required|optional)",
        )
        for pattern in negative_patterns:
            if re.search(pattern, normalized, re.IGNORECASE):
                return False

        positive_patterns = (
            r"(문의|상담|전화).{0,8}(필수|필요|요망|후)",
            r"(예약|당일).{0,12}(문의|상담|전화).{0,8}(필수|필요|요망)",
            r"(call|phone|contact|inquiry).{0,12}(required|must|needed)",
        )
        for pattern in positive_patterns:
            if re.search(pattern, normalized, re.IGNORECASE):
                return True

        return False

    @staticmethod
    def _sanitize_display_name(name: str) -> str:
        """지점 display_name에서 예약 안내 문구, 대괄호 태그를 제거한다."""
        if not name:
            return name
        # 대괄호 태그 제거: [밴드 합주, 드럼 개인연습 전용] 등
        cleaned = re.sub(r"\[.*?\]", "", name).strip()
        # 예약/안내 문구 제거
        cleaned = re.sub(r"\s*(예약|방문\s*상담|문의|안내)$", "", cleaned).strip()
        return cleaned if cleaned else name

    # 밴드 합주실 최소 가격 기준 (원/시간)
    # 개인연습실(피아노, 보컬 등)은 보통 3,000~6,000원대이므로
    # 7,000원 미만은 합주실이 아닐 가능성이 높아 수집 대상에서 제외한다.
    MIN_REHEARSAL_PRICE = 7000

    def _has_reservation_metadata(self, room: Dict[str, Any]) -> bool:
        """룸에 파싱할 충분한 예약 메타데이터가 있는지 확인한다.

        가격 정보는 필수이며, 밴드 합주실 최소 가격(MIN_REHEARSAL_PRICE) 이상이어야 한다.
        개인연습실 등 저가 룸은 합주실이 아닐 가능성이 높으므로 수집에서 제외한다.
        """
        base_price = self._extract_price(room)
        if isinstance(base_price, int) and base_price >= self.MIN_REHEARSAL_PRICE:
            return True

        raw_price = self._coerce_int(room.get("price"))
        if raw_price is not None and raw_price >= self.MIN_REHEARSAL_PRICE:
            return True

        return False

    @staticmethod
    def _has_non_empty_payload(value: Any) -> bool:
        """비어있지 않은 JSON 형태의 페이로드이면 True를 반환한다."""
        if value is None:
            return False
        if isinstance(value, str):
            text = value.strip()
            if not text:
                return False
            try:
                parsed = json.loads(text)
            except json.JSONDecodeError:
                return True
            return RoomCollectionService._has_non_empty_payload(parsed)
        if isinstance(value, dict):
            return len(value) > 0
        if isinstance(value, list):
            return len(value) > 0
        return True

    @staticmethod
    def _collect_room_policy_texts(room: Dict[str, Any]) -> List[str]:
        """문의 감지를 위한 정책 관련 텍스트 스니펫을 수집한다."""
        texts: List[str] = []

        def walk(value: Any) -> None:
            if isinstance(value, str):
                stripped = value.strip()
                if stripped:
                    texts.append(stripped)
                return
            if isinstance(value, list):
                for item in value:
                    walk(item)
                return
            if isinstance(value, dict):
                for nested_value in value.values():
                    walk(nested_value)

        walk(room.get("name"))
        walk(room.get("desc"))
        walk(room.get("extraDescJson"))
        walk(room.get("bookingPrecautionJson"))
        return texts

    def _extract_structured_requires_call_on_same_day(self, room: Dict[str, Any]) -> Optional[bool]:
        """구조화된 JSON 필드에서 당일 예약 연락 필요 여부를 추출한다."""
        candidate_fields = [
            room.get("extraDescJson"),
            room.get("bookingCountSettingJson"),
            room.get("extraFeeSettingJson"),
            room.get("additionalPropertyJson"),
        ]

        parsed_candidates = []
        for field in candidate_fields:
            if isinstance(field, str):
                try:
                    parsed_candidates.append(json.loads(field))
                except json.JSONDecodeError:
                    continue
            else:
                parsed_candidates.append(field)

        key_hints_strict = (
            "requirescallonsameday",
            "requirecallonsameday",
            "sameDayCallRequired",
            "phoneInquiryRequired",
            "contactRequired",
        )
        key_hints_loose_a = ("same", "today", "day")
        key_hints_loose_b = ("call", "phone", "contact", "inquiry", "consult", "confirm")

        def walk(obj: Any) -> Optional[bool]:
            if isinstance(obj, dict):
                for key, value in obj.items():
                    key_str = str(key)
                    key_lower = key_str.lower()

                    if any(hint.lower() in key_lower for hint in key_hints_strict):
                        coerced = self._coerce_bool(value)
                        if coerced is not None:
                            return coerced

                    if any(token in key_lower for token in key_hints_loose_a) and any(
                        token in key_lower for token in key_hints_loose_b
                    ):
                        coerced = self._coerce_bool(value)
                        if coerced is not None:
                            return coerced

                    nested = walk(value)
                    if nested is not None:
                        return nested
            elif isinstance(obj, list):
                for item in obj:
                    nested = walk(item)
                    if nested is not None:
                        return nested
            return None

        def collect_texts(obj: Any, out: List[str]):
            if isinstance(obj, dict):
                for value in obj.values():
                    collect_texts(value, out)
            elif isinstance(obj, list):
                for item in obj:
                    collect_texts(item, out)
            elif isinstance(obj, str):
                out.append(obj)

        for candidate in parsed_candidates:
            result = walk(candidate)
            if result is not None:
                return result

            # 구조화 텍스트 블록 fallback (예: extraDescJson[].title/context)
            texts: List[str] = []
            collect_texts(candidate, texts)
            if texts:
                joined = " ".join(texts).lower()

                has_same_day = any(token in joined for token in ["당일", "same day", "same-day", "today", "오늘"])
                has_call = any(
                    token in joined
                    for token in ["전화", "문의", "call", "phone", "contact", "inquiry", "consult", "confirm"]
                )
                has_negative = any(
                    token in joined
                    for token in ["없이", "불필요", "필요없", "not required", "no need", "without"]
                )

                # 강한 긍정: 당일 + 전화/문의 신호
                if has_same_day and has_call and not has_negative:
                    return True

                # 구조화 텍스트 내 명시적 부정 표현
                if has_same_day and has_call and has_negative:
                    return False
        return None

    def _extract_price(self, room: Dict) -> Optional[int]:
        """데이터가 부족한 페이로드에 대비한 fallback과 함께 가격 정보를 추출한다."""
        min_max = room.get("minMaxPrice")
        if isinstance(min_max, dict):
            # 1차 소스: 예약 GraphQL 최저 가격
            min_price = self._coerce_int(min_max.get("minPrice"))
            if min_price is not None and min_price >= 0:
                return min_price

        # 2차 소스: 직접 price 필드
        direct_price = self._coerce_int(room.get("price"))
        if direct_price is not None and direct_price >= 0:
            return direct_price

        # 최후 수단: 룸 이름/설명 내 텍스트 힌트 (예: "(18,000원/1시간)")
        for text in (room.get("name"), room.get("desc")):
            if not isinstance(text, str) or not text.strip():
                continue
            for raw in re.findall(
                r"(\d[\d,\s]{2,})\s*(?:원|krw|won)",
                text,
                flags=re.IGNORECASE,
            ):
                candidate = self._coerce_int(raw)
                if candidate is not None and candidate >= 1000:
                    return candidate
        return None

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
            parsed_range: 파서가 파싱한 범위 ([min, max] 형태)
            rec_cap: 권장 인원 수
            max_cap: 최대 인원 수
            base_cap: 기준 인원 수 (추가 요금 계산 기준)
            extra_charge: 추가 요금 (원)

        Returns:
            [min, max] 형태의 권장 인원 범위 리스트

        Rationale:
            1. 파싱된 범위가 유효하면 우선 사용 (단 합리적 범위로 clamp)
            2. 추가 요금 발생 시 [base_cap, max_cap]
            3. 추가 요금 없을 시 rec_cap ±delta (rec_cap < 9: ±1, rec_cap >= 9: ±2)
        """
        # 1. 파싱된 범위 검증 후 우선 사용
        # 조건: 2개 숫자(int 또는 float), min <= max, 합주실 현실적 범위(1~50명 이내)
        # NOTE: 파서가 float(예: 4.0)을 반환할 수 있으므로 int/float 모두 허용
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
        # rec_cap 기준 ±delta로 범위 산출
        # rec_cap < 9: ±1 (소규모 룸은 좁은 범위)
        # rec_cap >= 9: ±2 (대규모 룸은 넓은 범위)
        delta = 2 if rec_cap >= 9 else 1
        min_c = max(rec_cap - delta, 1)
        max_c = min(rec_cap + delta, max_cap)

        # max_cap이 너무 작아 min_c > max_c가 되는 경우 방어
        max_c = max(max_c, min_c)

        return [min_c, max_c]

    async def _export_unresolved(self, business: Dict, rooms: List[Dict], parsed_results: Dict):
        """
        Export unresolved parsing results to JSON file for manual verification.

        Phase 6: When parsing is incomplete (especially when no capacity info is found),
        export the original crawled text to a JSON file for later manual verification.
        """
        unresolved_items = []
        business_id = str(business.get("businessId") or business.get("id") or "").strip() or "unknown_business"
        business_name = (
            str(business.get("businessDisplayName") or business.get("name") or "").strip()
            or business_id
        )

        for room in rooms:
            rid = room["bizItemId"]
            parsed = parsed_results.get(rid, {})

            # 수용 인원 파싱 실패 기준으로 미해결 항목 식별
            max_capacity = parsed.get("max_capacity")
            failure_reason = None

            if max_capacity is None:
                failure_reason = "no_capacity_info"
            elif max_capacity == self.MANUAL_REVIEW_FLAG:
                failure_reason = "manual_review_flag"

            # 실패 사유가 있을 때만 내보내기
            if failure_reason:
                unresolved_item = {
                    "business_id": business_id,
                    "business_name": business_name,
                    "biz_item_id": rid,
                    "raw_name": room.get("name", ""),
                    "raw_desc": room.get("desc"),
                    "parsed_result": parsed,
                    "failure_reason": failure_reason,
                    "price_per_hour": self._extract_price(room),
                    "exported_at": datetime.now().isoformat()
                }
                unresolved_items.append(unresolved_item)

        # 미해결 항목이 있으면 파일로 내보내기
        if unresolved_items:
            # 로컬 환경에서 호출 시 경로 설정 가능. 기본값은 프로젝트 루트/scripts/unresolved
            default_dir = Path(__file__).parent.parent.parent / "scripts" / "unresolved"
            export_dir = Path(os.getenv("UNRESOLVED_EXPORT_DIR", str(default_dir)))
            export_dir.mkdir(parents=True, exist_ok=True)

            # 현재 날짜로 파일명 생성
            date_str = datetime.now().strftime("%Y%m%d")
            export_file = export_dir / f"unresolved_{date_str}.json"

            # 기존 파일이 있으면 불러오고, 없으면 빈 리스트로 시작
            existing_data = []
            if export_file.exists():
                try:
                    with open(export_file, "r", encoding="utf-8") as f:
                        existing_data = json.load(f)
                except Exception as e:
                    logger.warning(f"Failed to read existing unresolved file: {e}")

            # 중복 체크 후 새 미해결 항목 추가
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



