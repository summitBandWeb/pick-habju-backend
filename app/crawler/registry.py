from typing import Dict, List, Optional
from threading import Lock
from app.crawler.base import BaseCrawler

class CrawlerRegistry:
    _instance: Optional["CrawlerRegistry"] = None
    _lock: Lock = Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._crawlers = {}
        return cls._instance

    def register(self, name: str, crawler: BaseCrawler):
        self._crawlers[name] = crawler

    def get(self, name: str) -> BaseCrawler:
        return self._crawlers.get(name)

    def get_all(self) -> List[BaseCrawler]:
        return list(self._crawlers.values())

    def get_all_as_dict(self) -> Dict[str, BaseCrawler]:
        return self._crawlers.copy()

# Global registry instance
registry = CrawlerRegistry()
