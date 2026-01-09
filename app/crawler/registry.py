from typing import Dict, List, Optional
from app.crawler.base import BaseCrawler

class CrawlerRegistry:
    _instance: Optional['CrawlerRegistry'] = None
    _crawlers: Dict[str, BaseCrawler] = {}

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def register(self, name: str, crawler: BaseCrawler):
        self._crawlers[name] = crawler

    def get(self, name: str) -> BaseCrawler:
        return self._crawlers.get(name)

    def get_all(self) -> List[BaseCrawler]:
        return list(self._crawlers.values())
    
    def get_all_map(self) -> Dict[str, BaseCrawler]:
        """Returns a copy of the registered crawlers map."""
        return self._crawlers.copy()

# Global singleton instance
registry = CrawlerRegistry()
