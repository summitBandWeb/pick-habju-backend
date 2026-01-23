from typing import Protocol, List

class IFavoriteRepository(Protocol):
    """즐겨찾기 저장소 인터페이스 (Repository Pattern Protocol)"""
    
    def add(self, user_id: str, biz_item_id: str) -> bool:
        """
        즐겨찾기 추가
        
        Args:
            user_id (str): 사용자(기기) 식별 ID
            biz_item_id (str): 합주실 고유 ID
            
        Returns:
            bool: 생성 성공 시 True, 이미 존재하면 False
        """
        ...

    def delete(self, user_id: str, biz_item_id: str) -> None:
        """
        즐겨찾기 삭제
        
        Args:
            user_id (str): 사용자(기기) 식별 ID
            biz_item_id (str): 합주실 고유 ID
        """
        ...
        
    def exists(self, user_id: str, biz_item_id: str) -> bool:
        """
        즐겨찾기 존재 여부 확인
        
        Args:
            user_id (str): 사용자(기기) 식별 ID
            biz_item_id (str): 합주실 고유 ID
            
        Returns:
            bool: 존재하면 True, 없으면 False
        """
        ...
    
    def get_all(self, user_id: str) -> List[str]:
        """
        사용자의 즐겨찾기 목록 조회
        
        Args:
            user_id (str): 사용자(기기) 식별 ID
            
        Returns:
            List[str]: 즐겨찾기된 합주실 ID 목록
        """
        ...
