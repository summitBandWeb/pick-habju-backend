"""
합주실 예약 가능 여부 조회 서비스

이 모듈은 여러 합주실 플랫폼(Dream, Groove, Naver 등)의 크롤러를 통합하여
예약 가능 여부를 조회하는 서비스 계층을 제공합니다.

주요 기능:
- 여러 크롤러 병렬 실행으로 응답 속도 최적화
- 일부 크롤러 실패 시에도 성공한 결과는 반환 (Graceful Degradation)
- 크롤러별 에러를 로깅하되 API 응답은 정상 처리

비즈니스 맥락:
- Dream, Groove는 자체 크롤링, Naver는 예약 API 사용
- 각 플랫폼마다 다른 인증 방식 및 데이터 구조 사용
- Service Layer 패턴을 적용하여 비즈니스 로직을 API 라우터에서 분리

관련 이슈: #87
작성자: siul
최초 작성: 2026-01-09
"""

from __future__ import annotations
import asyncio
import logging
from app.models.dto import AvailabilityRequest, AvailabilityResponse, RoomAvailability
from app.validate.request_validator import validate_availability_request
from app.utils.room_router import filter_rooms_by_type
from app.crawler.base import BaseCrawler
from app.exception.base_exception import BaseCustomException
from typing import List
from datetime import datetime, timedelta
from app.utils.room_loader import get_rooms_by_capacity

logger = logging.getLogger("app")

class AvailabilityService:
    """합주실 예약 가능 여부 조회 서비스.
    
    여러 크롤러를 사용하여 동시에 예약 가능 여부를 조회하고,
    결과를 통합하여 반환합니다. 비즈니스 로직을 API 라우터에서 분리하여
    테스트 가능성과 재사용성을 높입니다.
    
    비즈니스 맥락:
    - Dream, Groove, Naver 등 여러 플랫폼의 합주실을 통합 조회
    - 각 플랫폼마다 다른 크롤러를 사용하여 데이터 수집
    - 일부 크롤러 실패 시에도 성공한 결과는 반환 (Graceful Degradation)
    
    설계 결정:
    - Dependency Injection을 통해 크롤러 주입 (테스트 용이성)
    - 비동기 병렬 처리로 응답 속도 최적화 (asyncio.gather 사용)
    - 에러를 Exception 객체로 반환하여 로깅 후 필터링
    
    사용 예시:
        >>> crawlers_map = {"dream": DreamCrawler(), "groove": GrooveCrawler()}
        >>> service = AvailabilityService(crawlers_map)
        >>> response = await service.check_availability(request)
    
    Attributes:
        crawlers_map: 크롤러 타입을 키로, BaseCrawler 인스턴스를 값으로 하는 딕셔너리
    """

    def __init__(self, crawlers_map: dict[str, BaseCrawler]):
        """서비스 초기화.
        
        Args:
            crawlers_map: 크롤러 타입(키)과 BaseCrawler 인스턴스(값)의 매핑 딕셔너리
                         예: {"dream": DreamCrawler(), "groove": GrooveCrawler()}
        """
        self.crawlers_map = crawlers_map

    # 시작시간과 종료시간으로 시간 슬롯 리스트 생성
    def generate_time_slots(self, start_str: str, end_str: str) -> List[str]:
        """
        start_hour와 end_hour 사이의 1시간 단위 슬롯 리스트를 생성합니다.
        예: 14:00 ~ 16:00 -> ["14:00", "15:00", "16:00"]
        """
        start_time = datetime.strptime(start_str, "%H:%M")
        end_time = datetime.strptime(end_str, "%H:%M")
        
        if start_time > end_time:
            raise ValueError("시작 시간이 종료 시간보다 같거나 늦을 수 없습니다.")

        slots = []
        current_time = start_time
        # 종료 시간 전까지만 슬롯 생성 (예: 14~16시면 14, 15, 16시 타임 예약 필요)
        while current_time <= end_time:
            slots.append(current_time.strftime("%H:%M"))
            current_time += timedelta(hours=1)
            
        return slots
        

    async def check_availability(self, request: AvailabilityRequest) -> AvailabilityResponse:
        """Check room availability across all registered crawlers."""

        # 1. 시간 범위(Range) -> 시간 슬롯 리스트(List) 변환
        # 예: 14:00 ~ 16:00 -> ["14:00", "15:00", "16:00"]
        try:
            hour_slots = self.generate_time_slots(request.start_hour, request.end_hour)
        except ValueError as e:
            logger.error(f"Time slot generation error: {e}")
            raise HTTPException(status_code=400, detail=str(e))
        
        # 2. 인원수에 맞는 룸 필터링 (DB 데이터 활용)
        target_rooms = get_rooms_by_capacity(request.capacity)

        validate_availability_request(request.date, hour_slots, target_rooms)

        # Prepare tasks for each crawler
        tasks = []
        for crawler_type, crawler in self.crawlers_map.items():
            filtered_rooms = filter_rooms_by_type(target_rooms, crawler_type)
            if filtered_rooms:
                tasks.append(crawler.check_availability(request.date, hour_slots, filtered_rooms))

        if not tasks:
            return AvailabilityResponse(
                date=request.date,
                hour_slots=hour_slots,
                results=[],
                available_biz_item_ids=[]
            )

        results_of_lists = await asyncio.gather(*tasks)
        all_results = [item for sublist in results_of_lists for item in sublist]

        self._log_errors(all_results, request.date)

        # Filter out exceptions (None check unnecessary per RoomResult type)
        successful_results = [r for r in all_results if not isinstance(r, Exception)]

        return AvailabilityResponse(
            date=request.date,
            hour_slots=hour_slots,
            results=successful_results,
            available_biz_item_ids=[r.room_detail.biz_item_id for r in successful_results if r.available is True]
        )

    def _log_errors(self, results: list[RoomAvailability | Exception], date_context: str):
        """크롤링 결과에서 에러를 추출하여 로깅.
        
        크롤러별 에러를 탐지하고 적절한 로그 레벨로 기록합니다.
        커스텀 예외는 Warning 레벨, 일반 예외는 Error 레벨로 로깅합니다.
        
        Args:
            results: RoomAvailability 또는 Exception이 혼재된 리스트
            date_context: 로그에 포함할 날짜 정보 (타임스탬프 대용)
            
        Note:
            - BaseCustomException: Warning 레벨 (예상된 에러, 예: 크롤링 실패)
            - 기타 Exception: Error 레벨 (예상치 못한 에러)
            
        TODO:
            Sentry 같은 모니터링 도구 연동 고려
            에러 발생률이 높을 경우 알림 기능 추가 필요
        """
        errors = [e for e in results if isinstance(e, Exception)]
        for err in errors:
            if isinstance(err, BaseCustomException):
                # 예상된 크롤러 에러 (Warning 레벨)
                logger.warning({
                    "timestamp": date_context,
                    "status": err.status_code,
                    "errorCode": err.error_code,
                    "message": err.message,
                })
            else:
                # 예상치 못한 일반 에러 (Error 레벨)
                logger.error({
                    "timestamp": date_context,
                    "status": 500,
                    "errorCode": "Common-001",
                    "message": str(err),
                })
