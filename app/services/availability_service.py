"""
?⑹＜???덉빟 媛???щ? 議고쉶 ?쒕퉬??

??紐⑤뱢? ?щ윭 ?⑹＜???뚮옯??Dream, Groove, Naver ?????щ·?щ? ?듯빀?섏뿬
?덉빟 媛???щ?瑜?議고쉶?섎뒗 ?쒕퉬??怨꾩링???쒓났?⑸땲??

二쇱슂 湲곕뒫:
- ?щ윭 ?щ·??蹂묐젹 ?ㅽ뻾?쇰줈 ?묐떟 ?띾룄 理쒖쟻??
- ?쇰? ?щ·???ㅽ뙣 ?쒖뿉???깃났??寃곌낵??諛섑솚 (Graceful Degradation)
- ?щ·?щ퀎 ?먮윭瑜?濡쒓퉭?섎릺 API ?묐떟? ?뺤긽 泥섎━

鍮꾩쫰?덉뒪 留λ씫:
- Dream, Groove???먯껜 ?щ·留? Naver???덉빟 API ?ъ슜
- 媛??뚮옯?쇰쭏???ㅻⅨ ?몄쬆 諛⑹떇 諛??곗씠??援ъ“ ?ъ슜
- Service Layer ?⑦꽩???곸슜?섏뿬 鍮꾩쫰?덉뒪 濡쒖쭅??API ?쇱슦?곗뿉??遺꾨━

愿???댁뒋: #87
?묒꽦?? siul
理쒖큹 ?묒꽦: 2026-01-09
"""

from __future__ import annotations
import asyncio
import logging
import re
from app.models.dto import (
    AvailabilityRequest, AvailabilityResponse,
    RoomAvailability, BranchStats, PolicyWarning
)
from app.validate.request_validator import validate_availability_request, validate_map_coordinates
from app.utils.room_router import filter_rooms_by_type
from app.crawler.base import BaseCrawler
from app.exception.base_exception import BaseCustomException, ErrorCode
from typing import List, Dict, Optional
from datetime import datetime
from app.utils.room_loader import get_rooms_by_criteria
from fastapi import HTTPException
from app.services.pricing_service import PricingService

logger = logging.getLogger("app")

class AvailabilityService:
    """?⑹＜???덉빟 媛???щ? 議고쉶 ?쒕퉬??
    
    ?щ윭 ?щ·?щ? ?ъ슜?섏뿬 ?숈떆???덉빟 媛???щ?瑜?議고쉶?섍퀬,
    寃곌낵瑜??듯빀?섏뿬 諛섑솚?⑸땲?? 鍮꾩쫰?덉뒪 濡쒖쭅??API ?쇱슦?곗뿉??遺꾨━?섏뿬
    ?뚯뒪??媛?μ꽦怨??ъ궗?⑹꽦???믪엯?덈떎.
    
    鍮꾩쫰?덉뒪 留λ씫:
    - Dream, Groove, Naver ???щ윭 ?뚮옯?쇱쓽 ?⑹＜?ㅼ쓣 ?듯빀 議고쉶
    - 媛??뚮옯?쇰쭏???ㅻⅨ ?щ·?щ? ?ъ슜?섏뿬 ?곗씠???섏쭛
    - ?쇰? ?щ·???ㅽ뙣 ?쒖뿉???깃났??寃곌낵??諛섑솚 (Graceful Degradation)
    
    ?ㅺ퀎 寃곗젙:
    - Dependency Injection???듯빐 ?щ·??二쇱엯 (?뚯뒪???⑹씠??
    - 鍮꾨룞湲?蹂묐젹 泥섎━濡??묐떟 ?띾룄 理쒖쟻??(asyncio.gather ?ъ슜)
    - ?먮윭瑜?Exception 媛앹껜濡?諛섑솚?섏뿬 濡쒓퉭 ???꾪꽣留?
    
    ?ъ슜 ?덉떆:
        >>> crawlers_map = {"dream": DreamCrawler(), "groove": GrooveCrawler()}
        >>> service = AvailabilityService(crawlers_map)
        >>> response = await service.check_availability(request)
    
    Attributes:
        crawlers_map: ?щ·????낆쓣 ?ㅻ줈, BaseCrawler ?몄뒪?댁뒪瑜?媛믪쑝濡??섎뒗 ?뺤뀛?덈━
    """

    def __init__(self, crawlers_map: dict[str, BaseCrawler]):
        """?쒕퉬??珥덇린??
        
        Args:
            crawlers_map: ?щ·???????怨?BaseCrawler ?몄뒪?댁뒪(媛???留ㅽ븨 ?뺤뀛?덈━
                         ?? {"dream": DreamCrawler(), "groove": GrooveCrawler()}
        """
        self.crawlers_map = crawlers_map
        self.pricing_service = PricingService()

    # ?쒖옉?쒓컙怨?醫낅즺?쒓컙?쇰줈 ?쒓컙 ?щ’ 由ъ뒪???앹꽦
    def generate_time_slots(self, start_str: str, end_str: str) -> List[str]:
        """
        start_hour? end_hour ?ъ씠??1?쒓컙 ?⑥쐞 ?щ’ 由ъ뒪?몃? ?앹꽦?⑸땲??
        ?? 14:00 ~ 16:00 -> ["14:00", "15:00", "16:00"]
        """
        start_min = self._slot_to_minutes(start_str)
        end_min = self._slot_to_minutes(end_str)

        if start_min > end_min:
            raise ValueError("?쒖옉 ?쒓컙??醫낅즺 ?쒓컙蹂대떎 ??쓣 ???놁뒿?덈떎.")
        if (end_min - start_min) % 60 != 0:
            raise ValueError("?쒖옉/醫낅즺 ?쒓컙? 1?쒓컙 ?⑥쐞?ъ빞 ?⑸땲??")

        slots = []
        current_min = start_min
        while current_min <= end_min:
            slots.append(self._minutes_to_slot(current_min))
            current_min += 60
            
        return slots

    def _slot_to_minutes(self, slot: str) -> int:
        """HH:MM 臾몄옄?댁쓣 遺??⑥쐞 ?뺤닔濡?蹂??24:00 ?덉슜)."""
        match = re.fullmatch(r"(\d{2}):(\d{2})", slot)
        if not match:
            raise ValueError(f"?쒓컙 ?뺤떇???щ컮瑜댁? ?딆뒿?덈떎: {slot}")
        hour = int(match.group(1))
        minute = int(match.group(2))
        if minute != 0:
            raise ValueError(f"?쒓컙? ?뺤떆(00遺?留?吏?먰빀?덈떎: {slot}")
        if hour < 0 or hour > 24:
            raise ValueError(f"?쒓컙 踰붿쐞媛 ?щ컮瑜댁? ?딆뒿?덈떎: {slot}")
        return hour * 60 + minute

    def _minutes_to_slot(self, minute_value: int) -> str:
        """遺??⑥쐞 媛믪쓣 HH:MM 臾몄옄?대줈 蹂??"""
        if minute_value == 1440:
            return "24:00"
        return f"{minute_value // 60:02d}:00"

    def _get_day_type(self, date_str: str) -> str:
        """?붿껌 ?좎쭨 湲곗? ?붿씪 ???weekday/weekend) 諛섑솚."""
        return "weekend" if datetime.strptime(date_str, "%Y-%m-%d").weekday() >= 5 else "weekday"

    def _is_slot_in_range(self, slot: str, start_hour: str, end_hour: str) -> bool:
        """slot??[start_hour, end_hour) 踰붿쐞???ы븿?섎뒗吏 ?먮떒."""
        try:
            slot_min = self._slot_to_minutes(slot)
            start_min = self._slot_to_minutes(start_hour)
            end_min = self._slot_to_minutes(end_hour)
        except ValueError:
            return False
        if start_min >= end_min:
            return False
        return start_min <= slot_min < end_min

    def _resolve_slot_price(self, room_detail, date_str: str, slot: str) -> int:
        """?⑥씪 ?щ’ 媛寃?怨꾩궛(price_config override + surcharge 諛섏쁺)."""
        day_type = self._get_day_type(date_str)
        price_config = room_detail.priceConfig or {}
        if not isinstance(price_config, dict):
            return max(int(room_detail.pricePerHour), 0)

        default_price = price_config.get("default")
        if not isinstance(default_price, (int, float)) or default_price < 0:
            default_price = room_detail.pricePerHour
        slot_price = int(default_price)

        overrides = price_config.get("overrides", [])
        if isinstance(overrides, list):
            for item in overrides:
                if not isinstance(item, dict):
                    continue
                if item.get("day_type") != day_type:
                    continue
                start_hour = item.get("start_hour")
                end_hour = item.get("end_hour")
                price = item.get("price")
                if (
                    isinstance(price, (int, float))
                    and isinstance(start_hour, str)
                    and isinstance(end_hour, str)
                    and self._is_slot_in_range(slot, start_hour, end_hour)
                ):
                    slot_price = int(price)

        surcharges = price_config.get("surcharges", [])
        if isinstance(surcharges, list):
            for item in surcharges:
                if not isinstance(item, dict):
                    continue
                if item.get("day_type") != day_type:
                    continue
                amount = item.get("amount")
                if isinstance(amount, (int, float)) and amount > 0:
                    slot_price += int(amount)

        return max(slot_price, 0)

    def calculate_total_price(self, room_detail, date_str: str, hour_slots: List[str]) -> int:
        """?붿껌 ?щ’ ?꾩껜??珥?媛寃?怨꾩궛."""
        if not hour_slots:
            return 0
        return sum(self._resolve_slot_price(room_detail, date_str, slot) for slot in hour_slots)
        

    async def check_availability(self, request: AvailabilityRequest) -> AvailabilityResponse:
        """Check room availability for a specific map area and criteria."""

        # 1. ?쒓컙 踰붿쐞(Range) -> ?쒓컙 ?щ’ 由ъ뒪??List) 蹂??
        # ?? 14:00 ~ 16:00 -> ["14:00", "15:00", "16:00"]
        try:
            hour_slots = self.generate_time_slots(request.start_hour, request.end_hour)
        except ValueError as e:
            logger.error(f"Time slot generation error: {e}")
            raise HTTPException(status_code=400, detail=str(e))
        
        # 1.5. 吏??醫뚰몴 ?좏슚??寃利?(?꾩닔)
        validate_map_coordinates(request.swLat, request.swLng, request.neLat, request.neLng)

        # 2. ?몄썝??諛?吏??踰붿쐞??留욌뒗 猷??꾪꽣留?(DB)
        target_rooms = get_rooms_by_criteria(
            capacity=request.capacity,
            swLat=request.swLat,
            swLng=request.swLng,
            neLat=request.neLat,
            neLng=request.neLng
        )

        validate_availability_request(request.date, hour_slots, target_rooms)

        # 3. ?щ·???묒뾽 以鍮?諛??ㅽ뻾
        tasks = []
        for crawler_type, crawler in self.crawlers_map.items():
            filtered_rooms = filter_rooms_by_type(target_rooms, crawler_type)
            if filtered_rooms:
                tasks.append(crawler.check_availability(request.date, hour_slots, filtered_rooms))

        if not tasks:
            return AvailabilityResponse(
                date=request.date,
                start_hour=request.start_hour,
                end_hour=request.end_hour,
                hour_slots=hour_slots,
                available_biz_item_ids=[],
                results=[],
                branch_summary={}
            )

        results_of_lists = await asyncio.gather(*tasks)
        all_results = [item for sublist in results_of_lists for item in sublist]

        self._log_errors(all_results, request.date)

        # 4. 寃곌낵 吏묎퀎 諛??뺤콉/媛寃??곸슜
        successful_results = [r for r in all_results if not isinstance(r, Exception)]
        processed_results = self._apply_policies(successful_results, request, hour_slots)
        
        available_results = []
        branch_summary = {}

        for res in processed_results:
            # 猷??뺣낫 異붿텧
            room_detail = res.room_detail

            # ?덉빟 媛?ν븳 猷몃쭔 寃곌낵 由ъ뒪?몄뿉 ?ы븿 (unknown ?ы븿)
            if res.available is True or res.available == "unknown":
                # v2.0.0: ?쒖떆??沅뚯옣 ?몄썝 踰붿쐞 怨꾩궛 (鍮꾩젙??max/base 議고빀 諛⑹뼱)
                rec_min: Optional[int] = None
                rec_max: Optional[int] = None

                if room_detail.baseCapacity and room_detail.baseCapacity > 0:
                    rec_min = room_detail.baseCapacity
                    if room_detail.maxCapacity and room_detail.maxCapacity >= rec_min:
                        rec_max = room_detail.maxCapacity
                    else:
                        fallback_max = room_detail.recommendCapacity or (rec_min + 2)
                        rec_max = max(rec_min, fallback_max)
                elif room_detail.recommendCapacityRange and len(room_detail.recommendCapacityRange) == 2:
                    rec_min, rec_max = room_detail.recommendCapacityRange
                elif room_detail.recommendCapacity and room_detail.recommendCapacity > 0:
                    rec_min = room_detail.recommendCapacity
                    rec_max = room_detail.recommendCapacity + 2

                if (
                    not room_detail.recommendCapacityRange
                    and rec_min is not None
                    and rec_max is not None
                    and rec_min > 0
                    and rec_max >= rec_min
                ):
                    room_detail.recommendCapacityRange = [rec_min, rec_max]

                if isinstance(res.estimated_price, int) and res.estimated_price > 0:
                    total_price = res.estimated_price
                else:
                    total_price = self.calculate_total_price(
                        room_detail=room_detail,
                        date_str=request.date,
                        hour_slots=hour_slots,
                    )

                available_results.append(res)

                # 吏???붿빟 ?뺣낫 ?낅뜲?댄듃 (branch_summary) - 吏??湲곕뒫??
                bid = room_detail.business_id
                if bid not in branch_summary:
                    branch_summary[bid] = BranchStats(
                        min_price=total_price,
                        available_count=1,
                        lat=room_detail.lat,
                        lng=room_detail.lng
                    )
                else:
                    stats = branch_summary[bid]
                    stats.available_count += 1
                    if total_price < stats.min_price:
                        stats.min_price = total_price

        return AvailabilityResponse(
            date=request.date,
            start_hour=request.start_hour,
            end_hour=request.end_hour,
            hour_slots=hour_slots,
            available_biz_item_ids=[r.room_detail.biz_item_id for r in available_results],
            results=available_results,
            branch_summary=branch_summary
        )



    def _log_errors(self, results: list[RoomAvailability | Exception], date_context: str):
        """?щ·留?寃곌낵?먯꽌 ?먮윭瑜?異붿텧?섏뿬 濡쒓퉭.
        
        ?щ·?щ퀎 ?먮윭瑜??먯??섍퀬 ?곸젅??濡쒓렇 ?덈꺼濡?湲곕줉?⑸땲??
        而ㅼ뒪? ?덉쇅??Warning ?덈꺼, ?쇰컲 ?덉쇅??Error ?덈꺼濡?濡쒓퉭?⑸땲??
        
        Args:
            results: RoomAvailability ?먮뒗 Exception???쇱옱??由ъ뒪??
            date_context: 濡쒓렇???ы븿???좎쭨 ?뺣낫 (??꾩뒪?ы봽 ???
            
        Note:
            - BaseCustomException: Warning ?덈꺼 (?덉긽???먮윭, ?? ?щ·留??ㅽ뙣)
            - 湲고? Exception: Error ?덈꺼 (?덉긽移?紐삵븳 ?먮윭)
            
        TODO:
            Sentry 媛숈? 紐⑤땲?곕쭅 ?꾧뎄 ?곕룞 怨좊젮
            ?먮윭 諛쒖깮瑜좎씠 ?믪쓣 寃쎌슦 ?뚮┝ 湲곕뒫 異붽? ?꾩슂
        """
        errors = [e for e in results if isinstance(e, Exception)]
        for err in errors:
            if isinstance(err, BaseCustomException):
                # ?덉긽???щ·???먮윭 (Warning ?덈꺼)
                logger.warning({
                    "timestamp": date_context,
                    "status": err.status_code,
                    "errorCode": err.error_code,
                    "message": err.message,
                })
            else:
                # ?덉긽移?紐삵븳 ?쇰컲 ?먮윭 (Error ?덈꺼)
                logger.error({
                    "timestamp": date_context,
                    "status": 500,
                    "errorCode": ErrorCode.COMMON_INTERNAL_ERROR,
                    "message": str(err),
                })

    def _apply_policies(
        self,
        results: List[RoomAvailability],
        request: AvailabilityRequest,
        hour_slots: List[str],
    ) -> List[RoomAvailability]:
        """정책 필터 및 가격 계산 적용"""
        today = datetime.now().strftime("%Y-%m-%d")
        processed: List[RoomAvailability] = []

        for res in results:
            room = res.room_detail
            policy_warnings: List[PolicyWarning] = []

            booking_duration_hours = len(hour_slots) - 1
            if booking_duration_hours == 1 and not room.canReserveOneHour:
                policy_warnings.append(
                    PolicyWarning(
                        type="call_required_1h",
                        message="1시간 예약은 전화 문의가 필요합니다.",
                    )
                )

            if request.date == today and room.requiresCallOnSameDay:
                policy_warnings.append(
                    PolicyWarning(
                        type="call_required_today",
                        message="당일 예약은 전화 문의가 필요합니다.",
                    )
                )

            if res.available is True:
                try:
                    if isinstance(room.priceConfig, dict):
                        price = self.calculate_total_price(room, request.date, hour_slots)
                    else:
                        normalized_rules = (
                            room.priceConfig
                            if isinstance(room.priceConfig, list)
                            and all(isinstance(cfg, dict) for cfg in room.priceConfig)
                            else []
                        )
                        start_dt = datetime.strptime(
                            f"{request.date} {hour_slots[0]}", "%Y-%m-%d %H:%M"
                        )
                        end_dt = datetime.strptime(
                            f"{request.date} {hour_slots[-1]}", "%Y-%m-%d %H:%M"
                        )
                        price = self.pricing_service.calculate_total_price(
                            base_price=room.pricePerHour,
                            price_config=normalized_rules,
                            base_capacity=room.baseCapacity,
                            extra_charge=room.extraCharge,
                            start_dt=start_dt,
                            end_dt=end_dt,
                            people_count=request.capacity,
                        )
                    res.estimated_price = price
                except ValueError as e:
                    logger.warning(f"Price calculation failed for {room.name}: {e}")
                    res.estimated_price = None

            res.policy_warnings = policy_warnings
            processed.append(res)

        return processed

