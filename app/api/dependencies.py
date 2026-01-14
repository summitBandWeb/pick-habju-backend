from __future__ import annotations
from fastapi import Depends
from app.crawler.base import BaseCrawler
from app.crawler.registry import registry
from app.services.availability_service import AvailabilityService


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
