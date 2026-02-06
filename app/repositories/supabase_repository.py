from typing import List, Optional
from app.repositories.base import IFavoriteRepository
from app.core.supabase_client import get_supabase_client
import logging

logger = logging.getLogger(__name__)

class SupabaseFavoriteRepository(IFavoriteRepository):
    """
    Supabase based Favorite Repository implementation.
    Uses 'favorites' table in Supabase.
    Composite Primary Key: (device_id, business_id, biz_item_id)
    """

    def __init__(self):
        self.supabase = get_supabase_client()
        self.table_name = "favorites"

    def add(self, device_id: str, business_id: str, biz_item_id: str) -> bool:
        """
        Adds a favorite item using upsert to handle idempotency.
        """
        try:
            data = {
                "device_id": device_id,
                "business_id": business_id,
                "biz_item_id": biz_item_id
            }
            # upsert=True is default for .upsert(), preventing duplicates on PK
            # returning='minimal' or 'representation'
            response = self.supabase.table(self.table_name).upsert(data).execute()
            
            # response.data would be non-empty if successful and returning data
            # Typically Supabase Python client returns an object with .data
            return True
        except Exception as e:
            logger.error(f"Error adding favorite: {e}")
            return False

    def delete(self, device_id: str, business_id: str, biz_item_id: str) -> None:
        """
        Deletes a favorite item.
        """
        try:
            self.supabase.table(self.table_name).delete().eq(
                "device_id", device_id
            ).eq(
                "business_id", business_id
            ).eq(
                "biz_item_id", biz_item_id
            ).execute()
        except Exception as e:
            logger.error(f"Error deleting favorite: {e}")

    def exists(self, device_id: str, business_id: str, biz_item_id: str) -> bool:
        """
        Checks if a favorite item exists using limit(1) for performance.
        """
        try:
            response = self.supabase.table(self.table_name).select(
                "", count="exact", head=True
            ).eq(
                "device_id", device_id
            ).eq(
                "business_id", business_id
            ).eq(
                "biz_item_id", biz_item_id
            ).execute()
            
            return response.count > 0
        except Exception as e:
            logger.error(f"Error checking existence: {e}")
            return False

    def get_all(self, device_id: str) -> List[str]:
        """
        Retrieves all favorite biz_item_ids for a device.
        """
        try:
            response = self.supabase.table(self.table_name).select(
                "biz_item_id"
            ).eq("device_id", device_id).execute()
            
            return [item["biz_item_id"] for item in response.data]
        except Exception as e:
            logger.error(f"Error fetching favorites: {e}")
            return []
