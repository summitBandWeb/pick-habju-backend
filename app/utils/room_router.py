from typing import Literal
from app.models.dto import RoomDetail

RoomType = Literal["dream", "groove", "naver"]


# business_id와 room_type 매핑 테이블
ID_MAP: dict[str, RoomType] = {
    "dream_sadang": "dream",
    "sadang": "groove",
    # 새로운 가게 생기면 여기에 한 줄 추가
    "hongdae_dream": "dream", 
}

def get_room_type(business_id: str) -> RoomType:
    # 매핑표에 있으면 그거 반환, 없으면 기본값 naver
    return ID_MAP.get(business_id, "naver")


def filter_rooms_by_type(rooms: list[RoomDetail], target_type: RoomType) -> list[RoomDetail]:
    return [room for room in rooms if get_room_type(room.business_id) == target_type]
