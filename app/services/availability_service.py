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
    RoomAvailability, PolicyWarning,
    BranchResponse, RoomResponse
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
        """서비스 초기화
        
        Args:
            crawlers_map: 플랫폼 타입을 키로 하고 BaseCrawler 인스턴스를 값으로 하는 매핑 딕셔너리
                         예: {"dream": DreamCrawler(), "groove": GrooveCrawler()}
        """
        self.crawlers_map = crawlers_map
        self.pricing_service = PricingService()

    # 시작시간과 종료시간으로 시간 슬롯 리스트 생성
    def generate_time_slots(self, start_str: str, end_str: str) -> List[str]:
        """시작 시간과 종료 시간 사이의 1시간 단위 예약 슬롯 리스트를 생성합니다.

        Args:
            start_str (str): 예약 시작 시간 문자열 (HH:MM 형식).
            end_str (str): 예약 종료 시간 문자열 (HH:MM 형식).

        Returns:
            List[str]: 1시간 단위로 분리된 슬롯 배열 (예: ["14:00", "15:00"]).

        Raises:
            ValueError: 시작/종료 시간이 정확히 1시간 단위가 아닐 때 발생. 

        Rationale (의도):
            사용자가 입력한 "시작~종료" 범위 구간을, 크롤러에 전달하고 응답과 대조하기 쉬운
            이산적인 1시간 단위 배열로 정규화하는 역할을 수행합니다.
            핵심 에러 검증(시작>종료 에외, 5시간 제한 등)은 DTO 계층으로 위임하고, 
            본 함수는 % 1440 모듈러 연산을 이용해 익일 슬롯 배열을 안정적으로 변환하는 것에 집중합니다.
        """
        start_min = self._slot_to_minutes(start_str)
        end_min = self._slot_to_minutes(end_str)

        # 예외 검증(시작=종료, 최대 5시간, 잘못된 심야 시간)은 이미 DTO 계층에서 처리 완료됨
        # 여기서는 오직 슬롯 배열 생성 로직에만 집중
        if start_min > end_min:
            end_min += 1440

        if (end_min - start_min) % 60 != 0:
            raise ValueError("시작/종료 시간은 1시간 단위여야 합니다.")

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
            raise ValueError(f"시간 형식이 올바르지 않습니다: {slot}")
        hour = int(match.group(1))
        minute = int(match.group(2))
        if minute != 0:
            raise ValueError(f"시간은 정시(00분)만 지원합니다: {slot}")
        if hour < 0 or hour > 24:
            raise ValueError(f"시간 범위가 올바르지 않습니다: {slot}")
        return hour * 60 + minute

    @staticmethod
    def _get_next_day_str(date_str: str) -> str:
        """날짜 문자열(YYYY-MM-DD)을 받아 익일 날짜문자열 반환"""
        dt = datetime.strptime(date_str, "%Y-%m-%d")
        next_dt = dt + timedelta(days=1)
        return next_dt.strftime("%Y-%m-%d")

    def _minutes_to_slot(self, minute_value: int) -> str:
        """분 단위 값을 HH:MM 문자열로 변환 (1440분 등 자정은 00:00으로 정규화)"""
        return f"{(minute_value % 1440) // 60:02d}:00"

    def _get_day_type(self, date_str: str) -> str:
        """요청 날짜 기준 요일 타입(weekday/weekend) 반환."""
        return "weekend" if datetime.strptime(date_str, "%Y-%m-%d").weekday() >= 5 else "weekday"

    def _is_slot_in_range(self, slot: str, start_hour: str, end_hour: str) -> bool:
        """slot이 [start_hour, end_hour) 범위에 포함되는지 판단."""
        try:
            slot_min = self._slot_to_minutes(slot)
            start_min = self._slot_to_minutes(start_hour)
            end_min = self._slot_to_minutes(end_hour)
        except ValueError:
            return False
        if start_min == end_min:
            return False
        
        if start_min > end_min:
            # 심야(Overnight) 요금 할증 등 시작 시간이 종료 시간보다 큰 경우 지원
            return slot_min >= start_min or slot_min < end_min
            
        return start_min <= slot_min < end_min

    def _resolve_slot_price(self, room_detail, date_str: str, slot: str) -> int:
        """단일 슬롯 가격 계산(price_config override + surcharge 반영)."""
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
        """요청 슬롯 전체의 총 가격 계산. (심야 예약 시 익일 날짜 반영 로직 포함)"""
        if len(hour_slots) < 2:
            return 0
            
        # [중요] 사용자가 요청한 시간 범위를 조회하기 위한 시작 슬롯들만 추출 (마지막 경계 슬롯 제외)
        billable_slots = hour_slots[:-1]
        
        total_price = 0
        current_date = date_str
        last_minutes = -1
        
        for slot in billable_slots:
            current_minutes = self._slot_to_minutes(slot)
            
            # 자정을 넘겼는지 체크 (이전 슬롯보다 분 단위가 작으면 날짜 변경)
            # NOTE: 슬롯이 1시간 단위로 연속적임이 검증되었다고 가정함.
            if last_minutes != -1 and current_minutes < last_minutes:
                current_date = self._get_next_day_str(current_date)
            
            total_price += self._resolve_slot_price(room_detail, current_date, slot)
            last_minutes = current_minutes
            
        return total_price
        

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

        # 1. 시간 범위(Range) -> 시간 슬롯 리스트(List) 변환
        # 예: 14:00 ~ 16:00 -> ["14:00", "15:00", "16:00"]
        try:
            hour_slots = self.generate_time_slots(request.start_hour, request.end_hour)
        except ValueError as e:
            logger.error(f"Time slot generation error: {e}")
            raise HTTPException(status_code=400, detail=str(e))
        
        # 1.5. 지도 좌표 유효성 검증 (필수) -> DTO model_validator로 이관됨

        # 2. 인원수 및 지도 범위에 맞는 룸 필터링(DB)
        target_rooms = get_rooms_by_criteria(
            capacity=request.capacity,
            swLat=request.swLat,
            swLng=request.swLng,
            neLat=request.neLat,
            neLng=request.neLng
        )
        
        validate_availability_request(request.date, hour_slots, target_rooms)

        # 3. 크롤러 비동기 작업 준비 및 실행
        tasks = []
        task_dates = []

        start_mins = self._slot_to_minutes(request.start_hour)
        end_min = self._slot_to_minutes(request.end_hour)
        is_overnight = (start_mins > end_min)
        
        # [중요] 사용자가 요청한 시간 범위를 조회하기 위한 시작 슬롯들만 추출 (마지막 경계 슬롯 제외)
        # 예: 23:00 ~ 01:00 요청 시 hour_slots는 ["23:00", "00:00", "01:00"] 이며,
        # 체크해야 할 시작 타임은 ["23:00", "00:00"] 입니다.
        slots_to_check = hour_slots[:-1]

        # [최적화] 루프 내부 반복 연산을 줄이기 위해 크롤러 루프 외부에서 1회만 계산
        if is_overnight:
            day1_slots = [slot for slot in slots_to_check if self._slot_to_minutes(slot) >= start_mins]
            day2_slots = [slot for slot in slots_to_check if slot not in day1_slots]
            next_date = self._get_next_day_str(request.date)
        else:
            day1_slots = slots_to_check
            day2_slots = []

        for crawler_type, crawler in self.crawlers_map.items():
            filtered_rooms = filter_rooms_by_type(target_rooms, crawler_type)
            if filtered_rooms:
                if is_overnight:
                    if day1_slots:
                        tasks.append(crawler.check_availability(request.date, day1_slots, filtered_rooms))
                        task_dates.append(request.date)
                    if day2_slots:
                        tasks.append(crawler.check_availability(next_date, day2_slots, filtered_rooms))
                        task_dates.append(next_date)
                else:
                    tasks.append(crawler.check_availability(request.date, day1_slots, filtered_rooms))
                    task_dates.append(request.date)

        if not tasks:
            return AvailabilityResponse(
                date=request.date,
                start_hour=request.start_hour,
                end_hour=request.end_hour,
                hour_slots=hour_slots,
                available_biz_item_ids=[],
                branches=[]
            )

        results_of_lists = await asyncio.gather(*tasks)
        
        all_results = []
        for res_list, t_date in zip(results_of_lists, task_dates, strict=True):
            for item in res_list:
                if isinstance(item, Exception):
                    item.date_context = t_date  # 익일 요청 실패 시의 날짜 추적을 위해 context 주입
                all_results.append(item)

        self._log_errors(all_results, request.date)

        # 4. 결과 집계 및 정책/가격 적용
        successful_results = [r for r in all_results if not isinstance(r, Exception)]
                # 심야 예약 분할 조회로 인한 동일 합주실(biz_item_id) 중복 데이터 병합
        merged_dict = {}
        for r in successful_results:
            biz_id = r.room_detail.biz_item_id
            if biz_id in merged_dict:
                existing = merged_dict[biz_id]
                
                # 1. 예약 가능 여부 병합 (AND 로직, 보수적 평가)
                if existing.available is True and r.available is True:
                    existing.available = True
                elif existing.available is False or r.available is False:
                    existing.available = False
                else:
                    existing.available = "unknown"
                    
                # 2. 각 시간대별 슬롯 가능 여부 딕셔너리 병합
                existing.available_slots.update(r.available_slots)
                
                # 3. 크롤러가 반환한 가격 병합
                if isinstance(existing.estimated_price, int) and isinstance(r.estimated_price, int):
                    existing.estimated_price += r.estimated_price
                elif isinstance(r.estimated_price, int):
                    existing.estimated_price = r.estimated_price
                    
                # 4. 정책 경고 로그 병합
                if hasattr(existing, 'policy_warnings') and hasattr(r, 'policy_warnings'):
                    existing.policy_warnings.extend(r.policy_warnings)
            else:
                merged_dict[biz_id] = r
                
        merged_results = list(merged_dict.values())
        processed_results = self._apply_policies(merged_results, request, hour_slots)
        
        branch_dict: Dict[str, BranchResponse] = {}
        available_ids: List[str] = []

        for res in processed_results:
            room_detail = res.room_detail

            # 예약 가능한 룸만 결과에 포함
            if res.available is True or res.available == "unknown":
                if isinstance(res.estimated_price, int) and res.estimated_price > 0:
                    total_price = res.estimated_price
                else:
                    total_price = self.calculate_total_price(
                        room_detail=room_detail,
                        date_str=request.date,
                        hour_slots=hour_slots,
                    )

                room_resp = RoomResponse(
                    biz_item_id=room_detail.biz_item_id,
                    name=room_detail.name,
                    price_per_hour=room_detail.pricePerHour,
                    available=res.available,
                    available_slots=res.available_slots,
                    estimated_price=total_price,
                    image_urls=room_detail.imageUrls,
                    max_capacity=room_detail.maxCapacity,
                    # [이슈 6] fallback 계산 제거됨 (recommendCapacity가 None이면 0이 될 수 있음, 클라이언트에서 처리 필요)
                    recommend_capacity=room_detail.recommendCapacityRange[1] if room_detail.recommendCapacityRange else 0, # TODO: 제거 예정 필드 (하위호환 유지용)
                    recommend_capacity_range=room_detail.recommendCapacityRange,
                    base_capacity=room_detail.baseCapacity,
                    extra_charge=room_detail.extraCharge,
                    min_capacity=room_detail.minCapacity,
                    min_hours=room_detail.minHours,
                    max_hours=room_detail.maxHours,
                    policy_warnings=res.policy_warnings
                )

                available_ids.append(room_detail.biz_item_id)
                bid = room_detail.business_id
                
                if bid not in branch_dict:
                    branch_dict[bid] = BranchResponse(
                        business_id=bid,
                        branch=room_detail.branch,
                        lat=room_detail.lat,
                        lng=room_detail.lng,
                        min_price=total_price,
                        available_count=1,
                        phone_number=room_detail.phoneNumber,
                        display_name=room_detail.displayName,
                        rooms=[room_resp]
                    )
                else:
                    branch_obj = branch_dict[bid]
                    branch_obj.rooms.append(room_resp)
                    branch_obj.available_count += 1
                    if total_price < branch_obj.min_price:
                        branch_obj.min_price = total_price

        return AvailabilityResponse(
            date=request.date,
            start_hour=request.start_hour,
            end_hour=request.end_hour,
            hour_slots=hour_slots,
            available_biz_item_ids=available_ids,
            branches=list(branch_dict.values())
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
            actual_date = getattr(err, 'date_context', date_context)
            if isinstance(err, BaseCustomException):
                # 예상된 플랫폼 에러 (Warning 레벨)
                logger.warning({
                    "timestamp": actual_date,
                    "status": err.status_code,
                    "errorCode": err.error_code,
                    "message": err.message,
                })
            else:
                # 예상치 못한 일반 에러 (Error 레벨)
                logger.error({
                    "timestamp": actual_date,
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
            # 기존 크롤러 등에서 넘어온 경고가 있을 수 있으므로 보존하면서 추가
            policy_warnings: List[PolicyWarning] = list(res.policy_warnings) if hasattr(res, 'policy_warnings') and res.policy_warnings else []

            # NOTE: hour_slots는 end-inclusive 슬롯 배열 (예: 14:00~16:00 → ["14:00","15:00","16:00"])
            #       따라서 예약 시간 = len - 1 로 정확히 계산됨.
            #       overnight 슬롯(예: ["23:00","00:00"]) 역시 len-1 = 1시간으로 정확히 계산됨.
            booking_duration_hours = len(hour_slots) - 1
            needs_1h_contact = (booking_duration_hours == 1 and not room.canReserveOneHour)
            needs_today_contact = (request.date == today and room.requiresContactOnSameDay)

            # 연락 수단 없는 방 사전 필터링
            # Rationale: phoneNumber/displayName 모두 없는 경우는 크롤러 미수집 문제임.
            #            이런 방에 정책이 적용되면 프론트에 전달할 type이 없으므로 제외함.
            #            장기 과제: 크롤러 phoneNumber/displayName 수집 안정화.
            if needs_1h_contact and not room.phoneNumber and not room.displayName:
                logger.warning(f"[policy_filter] biz_item_id={room.biz_item_id} excluded: no contact info for 1h reservation")
                continue
            
            # [Asymmetric Design Note]
            # 1h 예약은 chat_required_1h(네이버 톡톡 등) 노출을 허용하지만,
            # 당일 예약은 명세에 따라 "전화 문의"만 가능하도록 결정됨.
            # 따라서 displayName이 있어도 phoneNumber가 없으면 당일 예약 필터링에서 배제함.
            if needs_today_contact and not room.phoneNumber:
                logger.warning(f"[policy_filter] biz_item_id={room.biz_item_id} excluded: no phone number for today reservation")
                continue

            # 1시간 예약 불가 경고 생성
            if needs_1h_contact:
                if room.phoneNumber:
                    policy_warnings.append(PolicyWarning(
                        type="call_required_1h",
                        message="1시간 예약은 전화 문의가 필요합니다.",
                    ))
                else:
                    # displayName만 있는 경우 (위 필터링 통과 후 여기 도달)
                    policy_warnings.append(PolicyWarning(
                        type="chat_required_1h",
                        message="1시간 예약은 채팅 문의가 필요합니다.",
                    ))

            # 당일 예약 연락 필요 경고 생성 (항상 1가지 type)
            if needs_today_contact:
                # phoneNumber 있는 방만 여기 도달 (없으면 위 필터링에서 제외됨)
                policy_warnings.append(PolicyWarning(
                    type="call_required_today",
                    message="당일 예약은 전화 문의가 필요합니다.",
                ))

            # 최소/최대 예약 시간 정책 검사
            # Rationale: 합주실마다 최소(예: 2시간)/최대(예: 4시간) 예약 제한이 있음.
            #            요청 시간이 범위를 벗어날 경우, 프론트엔드가 안내 모달을 띄울 수 있도록 경고 추가.
            # NOTE: minHours/maxHours가 None이면 제한 없음으로 간주하여 검사 스킵.
            if room.minHours is not None and booking_duration_hours < room.minHours:
                policy_warnings.append(PolicyWarning(
                    type="min_hours_violation",
                    message=f"최소 {room.minHours}시간 이상 예약이 필요합니다.",
                ))
            if room.maxHours is not None and booking_duration_hours > room.maxHours:
                policy_warnings.append(PolicyWarning(
                    type="max_hours_violation",
                    message=f"최대 {room.maxHours}시간까지만 예약할 수 있습니다.",
                ))

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
                        end_dt = datetime.strptime(
                            f"{request.date} {end_slot}", "%Y-%m-%d %H:%M"
                        )
                        
                        # [심야 예약 대응] 종료 시간이 시작 시간보다 같거나 빠르면 익일로 간주
                        if end_dt <= start_dt:
                            end_dt += timedelta(days=1)
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

