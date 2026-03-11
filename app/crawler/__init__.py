from app.crawler.base import BaseCrawler
from app.crawler.registry import CrawlerRegistry, registry

# 모듈 임포트 시 크롤러를 등록하기 위해 임포트
from app.crawler import naver_checker, dream_checker, groove_checker

__all__ = ["BaseCrawler", "CrawlerRegistry", "registry"]
