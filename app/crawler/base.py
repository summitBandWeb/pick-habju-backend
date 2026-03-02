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

    @staticmethod
    def resolve_tri_state(available_slots: dict[str, bool], hour_slots: List[str] = None) -> bool:
        """
        주어진 슬롯 중 예약 가능한 시간(True)이 전부인지 확인합니다.
        하나라도 예약 불가(False)가 있다면 False를 반환합니다.
        
        Args:
            available_slots: 시간대별 예약 가능 여부 (예: {"18:00": True, "19:00": False})
            hour_slots: 검사할 시간대 리스트. None이면 available_slots 전체를 검사합니다.
            
        Returns:
            요청된 모든 슬롯이 가능하면 True, 하나라도 불가능하면 False.
        """
        values = [val for hour, val in available_slots.items() if (hour_slots is None or hour in hour_slots)]
        if not values:
            return False
            
        return all(values)
