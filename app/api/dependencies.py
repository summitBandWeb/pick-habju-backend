from __future__ import annotations
from fastapi import Depends
from app.crawler.base import BaseCrawler
from app.crawler.registry import registry
from app.services.availability_service import AvailabilityService

# --- Favorites API Dependencies ---
from app.repositories.base import IFavoriteRepository
from app.repositories.supabase import SupabaseFavoriteRepository
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

# Mock Repo Singleton Removed/Commented Out
# _mock_fav_repo = MockFavoriteRepository() 

from functools import lru_cache

@lru_cache(maxsize=1)
def get_favorite_repository() -> IFavoriteRepository:
    """
    Favorite Repository 의존성 주입 (Singleton via lru_cache)
    
    Returns:
        IFavoriteRepository: Supabase Repository 반환 (캐싱된 인스턴스)
    """
    return SupabaseFavoriteRepository()