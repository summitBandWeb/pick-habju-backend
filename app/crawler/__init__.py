from app.crawler.base import BaseCrawler
from app.crawler.registry import CrawlerRegistry, registry

# 크롤러 등록을 위해 import (사용하지 않아도 import만으로 등록됨)
from app.crawler import naver_checker, dream_checker, groove_checker

__all__ = ['BaseCrawler', 'CrawlerRegistry', 'registry']
