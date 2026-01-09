from typing import List, Dict
from app.crawler.base import BaseCrawler
from app.crawler.registry import registry

def get_crawlers() -> List[BaseCrawler]:
    """
    Returns a list of all registered crawler instances.
    """
    return registry.get_all()

def get_crawlers_map() -> Dict[str, BaseCrawler]:
    """
    Returns a dictionary of registered crawlers with their names as keys.
    """
    return registry.get_all_map()
