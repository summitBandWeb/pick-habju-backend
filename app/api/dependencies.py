from __future__ import annotations
from fastapi import Depends, Header, HTTPException
import uuid
from app.crawler.base import BaseCrawler
from app.crawler.registry import registry
from app.services.availability_service import AvailabilityService

# --- Favorites API Dependencies ---
from app.repositories.base import IFavoriteRepository
from app.repositories.supabase_repository import SupabaseFavoriteRepository
# from app.repositories.memory import MockFavoriteRepository


def get_crawlers() -> list[BaseCrawler]:
    """등록된 모든 크롤러 인스턴스 리스트 반환."""
    return registry.get_all()


def get_crawlers_map() -> dict[str, BaseCrawler]:
    """등록된 크롤러 맵 반환 (키: 크롤러 타입명)."""
    return registry.get_all_map()


def get_availability_service(
    crawlers_map: dict[str, BaseCrawler] = Depends(get_crawlers_map)
) -> AvailabilityService:
    """AvailabilityService 인스턴스 반환 (DI용)."""
    return AvailabilityService(crawlers_map)


from functools import lru_cache

@lru_cache(maxsize=1)
def get_favorite_repository() -> IFavoriteRepository:
    """
    Favorite Repository 의존성 주입 (Singleton via lru_cache)
    
    Returns:
        IFavoriteRepository: Supabase Repository 반환 (캐싱된 인스턴스)
    """
    return SupabaseFavoriteRepository()


def validate_device_id(
    x_device_id: str | None = Header(default=None, alias="X-Device-Id")
) -> str:
    """
    X-Device-Id 헤더 검증 및 반환 Dependency
    
    Raises:
        HTTPException(400): 헤더가 없거나 비어있는 경우, 또는 UUID 형식이 아닌 경우
    """
    if not x_device_id or not x_device_id.strip():
        raise HTTPException(
            status_code=400, 
            detail="X-Device-Id header is required and cannot be empty"
        )
    
    try:
        uuid.UUID(x_device_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid X-Device-Id format")
    
    return x_device_id
