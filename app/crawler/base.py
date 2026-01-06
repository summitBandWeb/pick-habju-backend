from abc import ABC, abstractmethod
from typing import List, Union
from app.models.dto import RoomKey, RoomAvailability

RoomResult = Union[RoomAvailability, Exception]

class BaseCrawler(ABC):
    @abstractmethod
    async def check_availability(self, date: str, hour_slots: List[str], rooms: List[RoomKey]) -> List[RoomResult]:
        """
        Check availability for the given rooms.
        """
        pass
