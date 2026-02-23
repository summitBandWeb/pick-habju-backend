"""
합주실 예약 가능 여부 조회 서비스

이 모듈은 여러 합주실 크롤러(Dream, Groove, Naver 등)를 통합하여
예약 가능 여부를 병렬로 조회하는 서비스 계층을 제공합니다.

주요 기능:
- 여러 크롤러의 병렬 실행(asyncio)으로 응답 속도 최적화
- 일부 크롤러 실패 시에도 성공한 결과 반환 (Graceful Degradation)
- 크롤러별 에러를 로깅하되 API 응답은 정상 처리 (서버 중단 방어)

비즈니스 맥락:
- Dream, Groove는 자체 크롤러, Naver는 예약 GraphQL API 사용
- 각 크롤러마다 다른 인증 방식 및 데이터 구조를 표준화
- Service Layer 패턴을 적용하여 비즈니스 로직을 API 라우터에서 분리 (관심사 분리)

관련 이슈: #87
작성자: siul
최초 작성: 2026-01-09
"""

from __future__ import annotations
import asyncio
import logging
import re
from app.models.dto import (
    AvailabilityRequest, AvailabilityResponse,
    RoomAvailability, BranchStats, PolicyWarning
)
from app.utils.room_router import filter_rooms_by_type
from app.crawler.base import BaseCrawler
from app.exception.base_exception import BaseCustomException, ErrorCode
from typing import List, Dict, Optional
from datetime import datetime, timedelta
from app.utils.room_loader import get_rooms_by_criteria
from fastapi import HTTPException
from app.services.pricing_service import PricingService
from app.validate.request_validator import validate_availability_request
from app.validate.room_detail_validator import validate_room_detail_list

logger = logging.getLogger("app")

class AvailabilityService:
    """합주실 예약 가능 여부 조회 서비스
    
    여러 크롤러를 사용하여 동시에 예약 가능 여부를 조회하고,
    결과를 통합하여 반환합니다. 비즈니스 로직을 API 라우터에서 분리하여
    테스트 가능성과 재사용성을 높입니다.
    
    비즈니스 맥락:
    - Dream, Groove, Naver 등 여러 플랫폼의 합주실을 통합 조회
    - 각 크롤러마다 다른 크롤링 기법을 사용하여 데이터 수집
    - 일부 크롤러 실패 시에도 성공한 결과 반환 (Graceful Degradation)
    
    설계 결정:
    - Dependency Injection을 통해 크롤러 주입 (테스트 용이성 확보)
    - 비동기 병렬 처리로 응답 속도 최적화 (asyncio.gather 사용)
    - 에러를 Exception 객체로 반환하여 로깅 및 필터링
    
    사용 예시:
        >>> crawlers_map = {"dream": DreamCrawler(), "groove": GrooveCrawler()}
        >>> service = AvailabilityService(crawlers_map)
        >>> response = await service.check_availability(request)
    
    Attributes:
        crawlers_map (dict): 크롤러 타입을 키로, BaseCrawler 인스턴스를 값으로 하는 딕셔너리
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
            raise ValueError("시작 시간이 종료 시간보다 늦을 수 없습니다.")
        if (end_min - start_min) % 60 != 0:
            raise ValueError("?쒖옉/醫낅즺 ?쒓컙? 1?쒓컙 ?⑥쐞?ъ빞 ?⑸땲??")

        slots = []
        current_min = start_min
        while current_min <= end_min:
            slots.append(self._minutes_to_slot(current_min))
            current_min += 60
            
        return slots

    def _slot_to_minutes(self, slot: str) -> int:
        """HH:MM 형식의 문자열을 분(Minutes) 단위 정수로 변환합니다. (24:00 허용)
        
        Args:
            slot (str): 시간 포맷 문자열 (예: "14:00")
            
        Returns:
            int: 00:00으로부터 경과된 '분' (예: "14:00" -> 840)
            
        Raises:
            ValueError: 형식이 맞지 않거나, 분 단위가 0이 아닐 경우
            
        Rationale (의도):
            문자열 기반의 타임라인 계산 시 대소 비교나 시간 간격 연산의 복잡도가 증가하므로,
            수치형 차원(Int) 연산으로 정규화하여 안정성을 높임.
        """
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
        if len(hour_slots) < 2:
            return 0
        # `hour_slots` is end-inclusive boundaries (e.g. ["14:00","15:00"] => 1 hour),
        # so only slots except the last boundary are billable.
        billable_slots = hour_slots[:-1]
        return sum(self._resolve_slot_price(room_detail, date_str, slot) for slot in billable_slots)
        

    async def check_availability(self, request: AvailabilityRequest) -> AvailabilityResponse:
        """조건에 맞는 합주실들의 예약 가능 여부를 일괄 조회합니다.

        Args:
            request (AvailabilityRequest): 클라이언트가 요청한 날짜, 시간, 위치, 인원 등의 필터 스펙

        Returns:
            AvailabilityResponse: 정상 조회된 방 리스트 및 에러/경고가 포맷팅된 최종 응답

        Raises:
            HTTPException: 400 (시간 슬롯 생성 실패 시 등)

        Rationale (의도):
            동기/비동기 크롤러를 혼합 호출하며, 에러가 발생한 크롤러(예: 네이버 블럭)가 
            전체 합주실 조회 서비스의 실패(500 서버 장애)로 이어지지 않도록 방어 로직을 구성함.
        """

        # 1. ?쒓컙 踰붿쐞(Range) -> ?쒓컙 ?щ’ 由ъ뒪??List) 蹂??
        # ?? 14:00 ~ 16:00 -> ["14:00", "15:00", "16:00"]
        try:
            hour_slots = self.generate_time_slots(request.start_hour, request.end_hour)
        except ValueError as e:
            logger.error(f"Time slot generation error: {e}")
            raise HTTPException(status_code=400, detail=str(e))
        
        # 1.5. 지도 좌표 유효성 검증 (필수) -> DTO model_validator로 이관됨

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
        """병렬 크롤러 결과에서 에러(Exception)만 추출하여 로깅합니다.
        
        Args:
            results (list[RoomAvailability | Exception]): 코루틴 gather를 통해 취합된 정상 응답 및 예외 객체 리스트
            date_context (str): 예약 요청일 (로그 추적 용도)
            
        Rationale (의도):
            크롤러가 1개 실패해도 전체 서비스는 계속 진행되지만 백엔드 개발자는 실패 사실을 알아야 하므로
            예상된 에러(비즈니스 예외)는 Warning으로, 크롤링 구조 변경 등 치명적 에러는 Error로 나눠 슬랙/로그 알림.
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
        """크롤링된 각 합주실의 비즈니스 정책(최소 인원 등) 및 동적 가격을 정산하여 방 필터링 및 할당.

        Args:
            results (List[RoomAvailability]): 크롤러에서 성공적으로 반환된 방 정보 리스트
            request (AvailabilityRequest): 사용자의 예약 필터 요건
            hour_slots (List[str]): 예약할 시간 슬롯들

        Returns:
            List[RoomAvailability]: 가격 책정 및 정책 필터링(보정)이 끝난 최종 클라이언트 응답용 방 배열

        Rationale (의도):
            단순 수집 결과(Raw Data)를 프론트엔드에 넘기기 전에 서버 자체 가격 계산기(PricingService)와 
            예약 조건(당일 예약 불가, 1시간 전화 등)을 검사/기입하기 위함.
        """
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
                        end_slot = hour_slots[-1]
                        if end_slot == "24:00":
                            end_dt = datetime.strptime(
                                f"{request.date} 00:00", "%Y-%m-%d %H:%M"
                            ) + timedelta(days=1)
                        else:
                            end_dt = datetime.strptime(
                                f"{request.date} {end_slot}", "%Y-%m-%d %H:%M"
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

