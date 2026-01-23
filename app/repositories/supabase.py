from typing import List, Any
from app.repositories.base import IFavoriteRepository
from app.core.supabase import get_supabase_client

class SupabaseFavoriteRepository(IFavoriteRepository):
    """
    Supabase (PostgreSQL) 기반 즐겨찾기 저장소 구현체
    테이블: favorites (user_id, biz_item_id)
    """

    def __init__(self):
        self.client = get_supabase_client()
        self.table = "favorites"

    def add(self, user_id: str, biz_item_id: str) -> bool:
        # 이미 존재하는지 확인 (Unique Violation 방지)
        # 만약 DB 레벨에서 upsert를 지원하면 upsert를 써도 되지만, 
        # 인터페이스 명세(bool 반환)를 맞추기 위해 체크 후 삽입 방식을 사용합니다.
        
        if self.exists(user_id, biz_item_id):
            return False
            
        try:
            self.client.table(self.table).insert({
                "user_id": user_id,
                "biz_item_id": biz_item_id
            }).execute()
            return True
        except Exception as e:
            # 중복 에러 등 발생 시 로그를 남기거나 False 처리
            # (실제 운영 시에는 구체적인 에러 핸들링 필요)
            print(f"Error adding favorite: {e}")
            return False

    def delete(self, user_id: str, biz_item_id: str) -> None:
        try:
            self.client.table(self.table)\
                .delete()\
                .eq("user_id", user_id)\
                .eq("biz_item_id", biz_item_id)\
                .execute()
        except Exception as e:
            print(f"Error deleting favorite: {e}")

    def exists(self, user_id: str, biz_item_id: str) -> bool:
        try:
            response = self.client.table(self.table)\
                .select("id", count="exact")\
                .eq("user_id", user_id)\
                .eq("biz_item_id", biz_item_id)\
                .execute()
            
            return response.count > 0
        except Exception as e:
            print(f"Error checking existence: {e}")
            return False

    def get_all(self, user_id: str) -> List[str]:
        try:
            response = self.client.table(self.table)\
                .select("biz_item_id")\
                .eq("user_id", user_id)\
                .execute()
            
            return [item["biz_item_id"] for item in response.data]
        except Exception as e:
            print(f"Error getting favorites: {e}")
            return []
