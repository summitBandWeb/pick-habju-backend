from typing import Set, Tuple, List
from app.repositories.base import IFavoriteRepository

class MockFavoriteRepository(IFavoriteRepository):
    """
    In-Memory Mock 저장소 구현체
    
    Note:
        서버 재시작 시 데이터가 초기화됩니다.
        (device_id, business_id, biz_item_id) 튜플을 Set으로 관리하여 중복을 방지합니다.
    """
    
    def __init__(self):
        """빈 In-Memory Set 저장소를 초기화한다."""
        # Data Structure: {(device_id, business_id, biz_item_id), ...}
        self._data: Set[Tuple[str, str, str]] = set()

    def add(self, device_id: str, business_id: str, biz_item_id: str) -> bool:
        """즐겨찾기 항목을 추가한다.

        이미 존재하는 항목이면 추가하지 않고 False를 반환한다.

        Args:
            device_id: 디바이스 식별자.
            business_id: 업체 식별자.
            biz_item_id: 룸 식별자.

        Returns:
            bool: 새로 추가되었으면 True, 이미 존재하면 False.
        """
        if self.exists(device_id, business_id, biz_item_id):
            return False

        self._data.add((device_id, business_id, biz_item_id))
        return True

    def delete(self, device_id: str, business_id: str, biz_item_id: str) -> None:
        """즐겨찾기 항목을 삭제한다.

        Args:
            device_id: 디바이스 식별자.
            business_id: 업체 식별자.
            biz_item_id: 룸 식별자.
        """
        if self.exists(device_id, business_id, biz_item_id):
            self._data.remove((device_id, business_id, biz_item_id))

    def exists(self, device_id: str, business_id: str, biz_item_id: str) -> bool:
        """즐겨찾기 항목의 존재 여부를 확인한다.

        Args:
            device_id: 디바이스 식별자.
            business_id: 업체 식별자.
            biz_item_id: 룸 식별자.

        Returns:
            bool: 존재하면 True, 아니면 False.
        """
        return (device_id, business_id, biz_item_id) in self._data

    def count_by_device(self, device_id: str) -> int:
        """특정 디바이스의 즐겨찾기 총 개수를 반환한다.

        Args:
            device_id: 디바이스 식별자.

        Returns:
            int: 즐겨찾기 항목 수.
        """
        return sum(1 for dev_id, _, _ in self._data if dev_id == device_id)

    def get_all(self, device_id: str) -> List[str]:
        """특정 디바이스의 모든 즐겨찾기 biz_item_id 목록을 반환한다.

        Args:
            device_id: 디바이스 식별자.

        Returns:
            List[str]: biz_item_id 리스트.
        """
        return [biz_id for dev_id, _, biz_id in self._data if dev_id == device_id]
