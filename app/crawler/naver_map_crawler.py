import os
import asyncio
import logging
from typing import List, Dict, Optional
from playwright.sync_api import sync_playwright
from concurrent.futures import ThreadPoolExecutor

logger = logging.getLogger(__name__)

class NaverMapCrawler:
    """네이버 지도에서 합주실을 검색하고 Business ID를 수집합니다."""
    
    BASE_URL = "https://pcmap.place.naver.com/place/list"
    
    # Configurable timeouts via environment variables
    PAGE_WAIT_MS = int(os.getenv("CRAWLER_PAGE_WAIT_MS", "3000"))
    SCROLL_WAIT_MS = int(os.getenv("CRAWLER_SCROLL_WAIT_MS", "1500"))
    MAX_PAGES = int(os.getenv("CRAWLER_MAX_PAGES", "5"))
    
    def __init__(self, headless: bool = True):
        self.headless = headless
        self._executor = ThreadPoolExecutor(max_workers=1)

    async def search_rehearsal_rooms(self, query: str = "합주실") -> List[Dict[str, str]]:
        """
        특정 키워드로 합주실을 검색하고 결과 목록을 반환합니다.
        Uses sync_playwright in a separate thread to avoid Windows asyncio issues.
        """
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(self._executor, self._search_sync, query)

    def _search_sync(self, query: str) -> List[Dict[str, str]]:
        """Synchronous search implementation."""
        results = {}
        
        with sync_playwright() as p:
            # Use channel='chrome' for more realistic browser fingerprint
            browser = p.chromium.launch(
                headless=self.headless,
                args=[
                    '--disable-blink-features=AutomationControlled',
                    '--no-sandbox',
                ]
            )
            context = browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                extra_http_headers={"Referer": "https://map.naver.com/"},
                viewport={"width": 1920, "height": 1080},
                locale="ko-KR",
                timezone_id="Asia/Seoul"
            )
            # Override navigator.webdriver to avoid detection
            context.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
            page = context.new_page()
            
            try:
                # 1. 첫 페이지 이동
                url = f"{self.BASE_URL}?query={query}&display=70"
                logger.info(f"Searching: {query} -> {url}")
                page.goto(url)
                page.wait_for_load_state("networkidle")
                page.wait_for_timeout(self.PAGE_WAIT_MS)  # Wait for JS initialization
                
                # 2. 첫 페이지 데이터 추출
                initial_data = self._extract_apollo_state_sync(page)
                self._merge_results(results, initial_data)
                
                # 3. 페이지네이션 처리 (최대 MAX_PAGES 페이지)
                for i in range(2, self.MAX_PAGES + 1):
                    next_btn = page.get_by_role("link", name=str(i), exact=True)
                    
                    if next_btn.is_visible():
                        logger.info(f"Navigating to page {i}")
                        next_btn.click()
                        page.wait_for_timeout(1000)
                        page.wait_for_load_state("networkidle")
                        
                        page_data = self._extract_apollo_state_sync(page)
                        if not page_data:
                            break
                        self._merge_results(results, page_data)
                    else:
                        break
                        
            except Exception as e:
                logger.error(f"Error crawling {query}: {e}")
            finally:
                browser.close()
                
        return list(results.values())

    def _extract_apollo_state_sync(self, page) -> List[Dict]:
        """window.__APOLLO_STATE__ 변수에서 PlaceSummary 데이터 추출 (Sync version)"""
        return page.evaluate("""
            () => {
                const state = window.__APOLLO_STATE__;
                // Debug: Return useful message if state is missing
                if (!state) {
                     return ["NO_APOLLO_STATE", "URL:" + window.location.href, "BODY:" + document.body.innerHTML.substring(0, 500)];
                }
                
                const places = [];
                const keys = Object.keys(state);
                
                for (const key of keys) {
                    if (key.startsWith('PlaceSummary:')) {
                        const place = state[key];
                        places.push({
                            id: place.bookingBusinessId ?? key.split(':')[1],
                            name: place.name,
                            category: place.category,
                            address: place.address,
                            roadAddress: place.roadAddress,
                            x: place.x,
                            y: place.y
                        });
                    }
                }
                
                // If no places found, return some keys to help debugging
                if (places.length === 0) {
                    return keys.slice(0, 10).map(k => "DEBUG_KEY:" + k);
                }
                
                return places;
            }
        """)

    def _merge_results(self, target: Dict, source: List[Dict]):
        """중복 제거하며 결과 병합"""
        for item in source:
            if not isinstance(item, dict):
                logger.warning(f"Skipping non-dict item: {item}")
                continue
            if item["id"] not in target:
                target[item["id"]] = item

    async def crawl_all_regions(self) -> List[Dict]:
        """
        Crawl nationwide regions (Seoul 25 districts + Major Metropolitan Cities).
        Sequential execution for stability on Windows.
        Returns list of collected business Item dicts (deduplicated).
        """
        # Seoul 25 districts
        seoul_districts = [
            "강남구 합주실", "강동구 합주실", "강북구 합주실", "강서구 합주실", "관악구 합주실",
            "광진구 합주실", "구로구 합주실", "금천구 합주실", "노원구 합주실", "도봉구 합주실",
            "동대문구 합주실", "동작구 합주실", "마포구 합주실", "서대문구 합주실", "서초구 합주실",
            "성동구 합주실", "성북구 합주실", "송파구 합주실", "양천구 합주실", "영등포구 합주실",
            "용산구 합주실", "은평구 합주실", "종로구 합주실", "중구 합주실", "중랑구 합주실"
        ]
        
        # Major Metropolitan Cities & Areas
        major_cities = [
            "부산 합주실", "대구 합주실", "인천 합주실", "광주 합주실", "대전 합주실", "울산 합주실",
            "수원 합주실", "성남 합주실", "고양 합주실", "부천 합주실"
        ]
        
        all_queries = seoul_districts + major_cities
        logger.info(f"Starting sequential crawl for {len(all_queries)} regions...")
        
        all_results = {}

        for idx, query in enumerate(all_queries):
            logger.info(f"[{idx+1}/{len(all_queries)}] Searching: {query}")
            try:
                region_results = await self.search_rehearsal_rooms(query)
                logger.info(f"✅ Finished {query}: Found {len(region_results)} rooms")
                
                for item in region_results:
                    if item["id"] not in all_results:
                        all_results[item["id"]] = item
                        
                # Small delay between regions
                await asyncio.sleep(2)
                
            except Exception as e:
                logger.error(f"❌ Failed to crawl {query}: {e}")
            
        logger.info(f"Total unique businesses found nationwide: {len(all_results)}")
        return list(all_results.values())

# 수동 실행용
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    crawler = NaverMapCrawler(headless=False)
    results = asyncio.run(crawler.search_rehearsal_rooms("사당 합주실"))
    print(f"Total found: {len(results)}")
    for r in results[:5]:
        print(r)
