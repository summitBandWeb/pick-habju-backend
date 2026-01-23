from abc import ABC, abstractmethod
from typing import List, Union
from app.models.dto import RoomDetail, RoomAvailability

RoomResult = Union[RoomAvailability, Exception]

class BaseCrawler(ABC):
    """
    모든 크롤러가 구현해야 하는 기본 인터페이스.
    
    새로운 합주실 크롤러를 추가할 때:
    1. 이 클래스를 상속받아 구현
    2. check_availability 메서드 구현
    3. 모듈 하단에서 registry.register()로 등록
    
    Example:
        class NewCrawler(BaseCrawler):
            async def check_availability(self, ...):
                # 구현
                pass
        
        registry.register("new", NewCrawler())
    """
    @abstractmethod
    async def check_availability(self, date: str, hour_slots: List[str], target_rooms: List[RoomDetail]) -> List[RoomResult]:
        """
        주어진 날짜와 시간대에 대한 방 예약 가능 여부를 확인.
        
        Args:
            date: 조회할 날짜 (YYYY-MM-DD 형식)
            hour_slots: 조회할 시간대 리스트 (예: ["18:00", "19:00"])
            target_rooms: 조회할 방 정보 리스트
            
        Returns:
            RoomAvailability 또는 Exception 리스트
            - 성공 시: RoomAvailability 객체 반환
            - 실패 시: Exception 반환 (로깅용)
        """
        pass
