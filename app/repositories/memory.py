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
        # Data Structure: {(device_id, business_id, biz_item_id), ...}
        self._data: Set[Tuple[str, str, str]] = set()

    def add(self, device_id: str, business_id: str, biz_item_id: str) -> bool:
        if self.exists(device_id, business_id, biz_item_id):
            return False
        
        self._data.add((device_id, business_id, biz_item_id))
        return True

    def delete(self, device_id: str, business_id: str, biz_item_id: str) -> None:
        if self.exists(device_id, business_id, biz_item_id):
            self._data.remove((device_id, business_id, biz_item_id))

    def exists(self, device_id: str, business_id: str, biz_item_id: str) -> bool:
        return (device_id, business_id, biz_item_id) in self._data

    def get_all(self, device_id: str) -> List[str]:
        return [biz_id for dev_id, _, biz_id in self._data if dev_id == device_id]
