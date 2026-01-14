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
from app.models.dto import AvailabilityRequest, AvailabilityResponse, RoomAvailability, RoomKey
from app.validate.request_validator import validate_availability_request
from app.utils.room_router import filter_rooms_by_type
from app.crawler.base import BaseCrawler
from app.exception.base_exception import BaseCustomException

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

    async def check_availability(self, request: AvailabilityRequest) -> AvailabilityResponse:
        """요청된 방들의 예약 가능 여부를 확인.
        
        각 크롤러 타입에 맞는 방들을 필터링하고, 병렬로 크롤링을 수행한 후
        결과를 통합하여 반환합니다. 에러가 발생한 크롤러는 로깅만 하고
        성공한 결과만 반환합니다.
        
        실행 흐름:
        1. 요청 데이터 검증 (날짜, 시간대, 방 목록)
        2. 크롤러별로 담당할 방 목록을 필터링하여 비동기 태스크 생성
        3. 모든 크롤러를 병렬 실행 (asyncio.gather)
        4. 결과 병합 및 에러 로깅
        5. 성공한 결과만 필터링하여 응답 생성
        
        Args:
            request: 날짜, 시간대, 조회할 방 목록을 포함한 요청 객체
                    - date: 조회 날짜 (YYYY-MM-DD)
                    - hour_slots: 시간대 리스트 (예: ["18:00", "19:00"])
                    - rooms: 방 정보 리스트 (business_id, item_id)
            
        Returns:
            예약 가능 여부 정보를 담은 응답 객체
            - date, hour_slots: 요청한 날짜 및 시간대 (에코)
            - results: 각 방의 예약 가능 여부 리스트 (성공한 크롤링 결과만)
            - available_biz_item_ids: 예약 가능한 방의 biz_item_id 목록
            
        Note:
            일부 크롤러가 실패해도 전체 요청은 성공으로 처리됩니다.
            실패한 크롤러는 로그에만 기록되며, 가용한 결과만 반환합니다.
            모든 크롤러가 실패하거나 요청된 방이 없으면 빈 결과를 반환합니다.
        """
        # 요청 데이터 검증 (날짜 형식, 시간대 범위, 방 목록 유효성)
        validate_availability_request(request.date, request.hour_slots, request.rooms)

        # 각 크롤러 타입별로 담당할 방을 필터링하여 병렬 실행 준비
        # 예: Dream 크롤러는 dream_sadang, hongdae_dream 방만 처리
        tasks = []
        for crawler_type, crawler in self.crawlers_map.items():
            target_rooms = filter_rooms_by_type(request.rooms, crawler_type)
            if target_rooms:
                tasks.append(crawler.check_availability(request.date, request.hour_slots, target_rooms))

        # 요청된 방이 없거나 모든 크롤러가 할당되지 않은 경우 빈 응답 반환
        if not tasks:
            return AvailabilityResponse(
                date=request.date,
                hour_slots=request.hour_slots,
                results=[],
                available_biz_item_ids=[]
            )

        # 모든 크롤러를 병렬 실행 (일부 실패해도 계속 진행)
        results_of_lists = await asyncio.gather(*tasks)
        
        # 중첩 리스트를 평탄화: [[R1, R2], [R3]] -> [R1, R2, R3]
        all_results = [item for sublist in results_of_lists for item in sublist]

        # 실패한 크롤러 에러 로깅 (Warning 또는 Error 레벨)
        self._log_errors(all_results, request.date)

        # Exception을 제외하고 성공한 결과만 필터링
        successful_results = [r for r in all_results if not isinstance(r, Exception)]

        return AvailabilityResponse(
            date=request.date,
            hour_slots=request.hour_slots,
            results=successful_results,
            available_biz_item_ids=[r.biz_item_id for r in successful_results if r.available is True]
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
