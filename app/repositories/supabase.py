from typing import List, Optional
import logging
from supabase import Client
from app.repositories.base import IFavoriteRepository
from app.core.supabase import get_supabase_client

# 로거 설정
logger = logging.getLogger(__name__)

class SupabaseFavoriteRepository(IFavoriteRepository):
    """
    Supabase (PostgreSQL) 기반 즐겨찾기 저장소 구현체
    테이블: favorites (user_id, biz_item_id)
    """

    def __init__(self, client: Optional[Client] = None):
        """
        Args:
            client (Optional[Client]): 테스트 용이성을 위한 의존성 주입 지원
        """
        self.client = client or get_supabase_client()
        self.table = "favorites"

    def add(self, user_id: str, biz_item_id: str) -> bool:
        """
        즐겨찾기 추가 (Upsert 사용)
        
        Rationale:
            - exists() + insert() 대신 upsert()를 사용하여 DB round-trip 감소 (성능 최적화)
            - on_conflict를 통해 중복 처리 자동화 (멱등성 보장)
        """
        try:
            # on_conflict를 사용한 upsert (Supabase v2 지원)
            # ignore_duplicates=False로 설정하여 업데이트(덮어쓰기) 동작 -> 결과 리턴됨
            response = self.client.table(self.table).upsert(
                {"user_id": user_id, "biz_item_id": biz_item_id},
                on_conflict="user_id,biz_item_id",
            ).execute()
            
            # 데이터가 성공적으로 처리되었으면 True 반환
            return len(response.data) > 0

        except Exception as e:
            # 에러 로깅 후 상위 호출자에게 전파 (Fail Fast)
            logger.error(f"Failed to add favorite for user {user_id}: {e}", exc_info=True)
            raise

    def delete(self, user_id: str, biz_item_id: str) -> None:
        try:
            self.client.table(self.table)\
                .delete()\
                .eq("user_id", user_id)\
                .eq("biz_item_id", biz_item_id)\
                .execute()
        except Exception as e:
            logger.error(f"Failed to delete favorite for user {user_id}: {e}", exc_info=True)
            raise

    def exists(self, user_id: str, biz_item_id: str) -> bool:
        """
        즐겨찾기 존재 여부 확인 (최적화)
        
        Rationale:
            - count="exact"는 전체 스캔을 유발할 수 있어 비효율적
            - limit(1)과 select("id")만 사용하여 확인
        """
        try:
            response = self.client.table(self.table)\
                .select("id")\
                .eq("user_id", user_id)\
                .eq("biz_item_id", biz_item_id)\
                .limit(1)\
                .execute()
            
            return len(response.data) > 0
        except Exception as e:
            logger.error(f"Failed to check existence for user {user_id}: {e}", exc_info=True)
            raise

    def get_all(self, user_id: str) -> List[str]:
        try:
            response = self.client.table(self.table)\
                .select("biz_item_id")\
                .eq("user_id", user_id)\
                .execute()
            
            return [item["biz_item_id"] for item in response.data]
        except Exception as e:
            logger.error(f"Failed to get favorites for user {user_id}: {e}", exc_info=True)
            raise
