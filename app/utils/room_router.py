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
    """business_id에 대응하는 룸 타입을 반환한다.

    ID_MAP 매핑 테이블에 존재하면 해당 타입을, 없으면 ``"naver"``를 기본값으로 반환한다.

    Args:
        business_id: 룸의 업체 식별자.

    Returns:
        ``"dream"``, ``"groove"``, ``"naver"`` 중 하나의 RoomType.
    """
    # 매핑표에 있으면 그거 반환, 없으면 기본값 naver
    return ID_MAP.get(business_id, "naver")


def filter_rooms_by_type(rooms: list[RoomDetail], target_type: RoomType) -> list[RoomDetail]:
    """지정된 타입에 해당하는 룸만 필터링하여 반환한다.

    Args:
        rooms: 필터링 대상 RoomDetail 리스트.
        target_type: 필터링 기준 RoomType (``"dream"``, ``"groove"``, ``"naver"``).

    Returns:
        target_type과 일치하는 룸만 포함된 리스트.
    """
    return [room for room in rooms if get_room_type(room.business_id) == target_type]
