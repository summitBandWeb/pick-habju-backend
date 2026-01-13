from app.crawler.base import BaseCrawler
from app.crawler.registry import CrawlerRegistry, registry

# Import crawlers to register them on module import.
from app.crawler import naver_checker, dream_checker, groove_checker

__all__ = ["BaseCrawler", "CrawlerRegistry", "registry"]
