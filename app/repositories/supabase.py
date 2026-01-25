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
    테이블: favorites (device_id, business_id, biz_item_id) - 복합 기본키
    """

    def __init__(self, client: Optional[Client] = None):
        """
        Args:
            client (Optional[Client]): 테스트 용이성을 위한 의존성 주입 지원
        """
        self.client = client or get_supabase_client()
        self.table = "favorites"

    def add(self, device_id: str, business_id: str, biz_item_id: str) -> bool:
        """
        즐겨찾기 추가 (Upsert 사용)
        
        Rationale:
            - exists() + insert() 대신 upsert()를 사용하여 DB round-trip 감소 (성능 최적화)
            - on_conflict를 통해 중복 처리 자동화 (멱등성 보장)
            - 복합 기본키(device_id, business_id, biz_item_id)로 충돌 감지
        """
        try:
            response = self.client.table(self.table).upsert(
                {
                    "device_id": device_id,
                    "business_id": business_id,
                    "biz_item_id": biz_item_id
                },
                on_conflict="device_id,business_id,biz_item_id",
            ).execute()
            
            return len(response.data) > 0

        except Exception as e:
            logger.error(f"Failed to add favorite for device {device_id}: {e}", exc_info=True)
            raise

    def delete(self, device_id: str, business_id: str, biz_item_id: str) -> None:
        try:
            self.client.table(self.table)\
                .delete()\
                .eq("device_id", device_id)\
                .eq("business_id", business_id)\
                .eq("biz_item_id", biz_item_id)\
                .execute()
        except Exception as e:
            logger.error(f"Failed to delete favorite for device {device_id}: {e}", exc_info=True)
            raise

    def exists(self, device_id: str, business_id: str, biz_item_id: str) -> bool:
        """
        즐겨찾기 존재 여부 확인 (최적화)
        
        Rationale:
            - count="exact"는 전체 스캔을 유발할 수 있어 비효율적
            - limit(1)과 복합키 조건으로 빠른 확인
        """
        try:
            response = self.client.table(self.table)\
                .select("device_id")\
                .eq("device_id", device_id)\
                .eq("business_id", business_id)\
                .eq("biz_item_id", biz_item_id)\
                .limit(1)\
                .execute()
            
            return len(response.data) > 0
        except Exception as e:
            logger.error(f"Failed to check existence for device {device_id}: {e}", exc_info=True)
            raise

    def get_all(self, device_id: str) -> List[str]:
        try:
            response = self.client.table(self.table)\
                .select("biz_item_id")\
                .eq("device_id", device_id)\
                .execute()
            
            return [item["biz_item_id"] for item in response.data]
        except Exception as e:
            logger.error(f"Failed to get favorites for device {device_id}: {e}", exc_info=True)
            raise
