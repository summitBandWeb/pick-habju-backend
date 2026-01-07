from typing import Callable, List, Awaitable, Union
from app.models.dto import RoomKey, RoomAvailability
from app.utils.room_router import RoomType
from app.crawler.dream_checker import get_dream_availability
from app.crawler.groove_checker import get_groove_availability
from app.crawler.naver_checker import get_naver_availability

RoomResult = Union[RoomAvailability, Exception]

CRAWLER_REGISTRY: dict[RoomType, Callable[[str, List[str], List[RoomKey]], Awaitable[List[RoomResult]]]] = {
    # "합주실 타입": 크롤러함수
    "dream": get_dream_availability,
    "groove": get_groove_availability,
    "naver": get_naver_availability, 
    # "hapjusil": get_hapjusil_availability,
    # "kakao": get_kakao_availability
}
