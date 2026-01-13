from typing import Dict, List
from app.crawler.base import BaseCrawler

class CrawlerRegistry:
    _crawlers: Dict[str, BaseCrawler] = {}

    @classmethod
    def register(cls, name: str, crawler: BaseCrawler):
        cls._crawlers[name] = crawler

    @classmethod
    def get(cls, name: str) -> BaseCrawler:
        return cls._crawlers.get(name)

    @classmethod
    def get_all(cls) -> List[BaseCrawler]:
        return list(cls._crawlers.values())

    @classmethod
    def get_all_as_dict(cls) -> Dict[str, BaseCrawler]:
        return cls._crawlers.copy()

# Global registry instance (optional, or just use class methods)
registry = CrawlerRegistry
