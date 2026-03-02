import os
import asyncio
import logging
from typing import List, Dict, Optional
from playwright.sync_api import sync_playwright
from concurrent.futures import ThreadPoolExecutor
from app.core.constants import SEOUL_DISTRICTS, MAJOR_CITIES
from fake_useragent import UserAgent

logger = logging.getLogger(__name__)

class NaverMapCrawler:
    """네이버 지도에서 합주실을 검색하고 Business ID를 수집합니다.
    
    주요 기능:
    - Sync Playwright 브라우저를 백그라운드 스레드에서 생성하여 합주실 검색
    - window.__APOLLO_STATE__ 전역 변수를 파싱하여 방/지점 객체 목록 확보
    
    Rationale (의도):
        - 네이버 지도는 SPA(단일 페이지 앱) 형태이므로 HTML Parsing이 불가하여 Headless 브라우저 기반 동적 렌더링을 씀.
        - Async Playwright가 Windows 환경에서 불안정할 수 있어 ThreadPoolExecutor와 sync_playwright 패턴으로 우회 처리.
    """
    
    BASE_URL = "https://pcmap.place.naver.com/place/list"
    
    # Configurable timeouts via environment variables
    PAGE_WAIT_MS = int(os.getenv("CRAWLER_PAGE_WAIT_MS", "3000"))
    SCROLL_WAIT_MS = int(os.getenv("CRAWLER_SCROLL_WAIT_MS", "1500"))
    MAX_PAGES = int(os.getenv("CRAWLER_MAX_PAGES", "5"))
    
    def __init__(self, headless: bool = True):
        self.headless = headless
        self._executor = ThreadPoolExecutor(max_workers=1)

    async def search_rehearsal_rooms(self, query: str = "합주실") -> List[Dict[str, str]]:
        """특정 키워드로 합주실을 검색하고 결과 목록을 반환합니다.
        
        Args:
            query (str): 네이버 지도에 검색할 지역명 + 합주실 키워드 (예: '사당 합주실')
            
        Returns:
            List[Dict[str, str]]: 파싱된 방 정보 딕셔너리 리스트 (id, name, address 등)
            
        Rationale (의도):
            - Windows asyncio 이벤트 루프와 Playwright 내부 루프 충돌을 방지하기 위해
              run_in_executor를 통해 별도의 스레드 풀에서 동기적으로 브라우저를 띄움.
        """
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(self._executor, self._search_sync, query)

    def _search_sync(self, query: str) -> List[Dict[str, str]]:
        """Synchronous search implementation."""
        # Optional dependencies import with fallback
        try:
            ua = UserAgent(fallback="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
            user_agent_str = ua.random
        except ImportError:
            logger.warning("fake-useragent not found. Using default user agent.")
            user_agent_str = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        except Exception as e:
            logger.warning(f"Error generating user agent: {e}. Using default.")
            user_agent_str = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

        results = {}
        
        with sync_playwright() as p:
            browser = None
            try:
                # 1. Try launching with 'chrome' channel (more realistic)
                browser = p.chromium.launch(
                    headless=self.headless,
                    channel="chrome",
                    args=[
                        '--disable-blink-features=AutomationControlled',
                        '--no-sandbox',
                    ]
                )
            except Exception as e:
                logger.warning(f"Failed to launch Chrome channel: {e}. Falling back to bundled Chromium.")
                try:
                    # 2. Fallback to bundled chromium
                    browser = p.chromium.launch(
                        headless=self.headless,
                        args=[
                            '--disable-blink-features=AutomationControlled',
                            '--no-sandbox',
                        ]
                    )
                except Exception as e2:
                    logger.error(f"Failed to launch bundled Chromium: {e2}")
                    return []

            context = browser.new_context(
                user_agent=user_agent_str,
                extra_http_headers={"Referer": "https://map.naver.com/"},
                viewport={"width": 1920, "height": 1080},
                locale="ko-KR",
                timezone_id="Asia/Seoul"
            )
            
            # Apply stealth if available
            try:
                from playwright_stealth import stealth_sync
                stealth_sync(context)
            except ImportError:
                logger.warning("playwright-stealth not found. Skipping stealth mode.")
            except Exception as e:
                logger.warning(f"Failed to apply stealth: {e}")

            # Override navigator.webdriver to avoid detection (redundant if stealth used, but safe)
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
        """window.__APOLLO_STATE__ 변수에서 PlaceSummary + 추가 데이터 추출 (Sync version)

        Rationale:
            PlaceSummary 외에 PlaceDetail(상세설명, 영업시간)과
            BookingBusiness(예약 메타데이터) 접두사도 수집하여
            GraphQL 호출 전에 확보 가능한 데이터를 최대화합니다.
            추가 데이터가 없어도 기존 동작에는 영향 없습니다.
        """
        return page.evaluate("""
            () => {
                const state = window.__APOLLO_STATE__;
                if (!state) {
                     return ["NO_APOLLO_STATE", "URL:" + window.location.href, "BODY_HIDDEN_FOR_SECURITY"];
                }
                
                const places = [];
                const details = {};    // placeId -> PlaceDetail 필드
                const bookings = {};   // placeId -> BookingBusiness 필드
                const keys = Object.keys(state);
                
                for (const key of keys) {
                    if (key.startsWith('PlaceSummary:')) {
                        const place = state[key];
                        places.push({
                            id: place.bookingBusinessId ?? key.split(':')[1],
                            placeId: key.split(':')[1],
                            name: place.name,
                            category: place.category,
                            address: place.address,
                            roadAddress: place.roadAddress,
                            x: place.x,
                            y: place.y
                        });
                    } else if (key.startsWith('PlaceDetail:')) {
                        const d = state[key];
                        const pid = key.split(':')[1];
                        details[pid] = {
                            description: d.description ?? d.desc ?? null,
                            businessHours: d.businessHours ?? null,
                            phone: d.phone ?? d.tel ?? null,
                            homepageUrl: d.homepageUrl ?? null
                        };
                    } else if (key.startsWith('BookingBusiness:')) {
                        const b = state[key];
                        const bid = key.split(':')[1];
                        bookings[bid] = {
                            bookingBusinessId: bid,
                            bookingUrl: b.bookingUrl ?? null,
                            businessCategory: b.businessCategory ?? null
                        };
                    }
                }
                
                // PlaceDetail/BookingBusiness 데이터를 PlaceSummary에 병합 (enrich)
                for (const place of places) {
                    const pid = place.placeId;
                    if (pid && details[pid]) {
                        Object.assign(place, details[pid]);
                    }
                    // bookingBusinessId가 있으면 BookingBusiness 데이터 병합
                    if (place.id && bookings[place.id]) {
                        Object.assign(place, bookings[place.id]);
                    }
                }
                
                if (places.length === 0) {
                    return ["NO_PLACES_FOUND_IN_APOLLO_STATE"];
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
            item_id = item.get("id")
            if not item_id:
                logger.warning(f"Skipping item without 'id': {list(item.keys())[:3]}")
                continue
            if item_id not in target:
                target[item_id] = item

    async def crawl_all_regions(self) -> List[Dict]:
        """
        Crawl nationwide regions (Seoul 25 districts + Major Metropolitan Cities).
        Sequential execution for stability on Windows.
        Returns list of collected business Item dicts (deduplicated).
        """
        all_queries = SEOUL_DISTRICTS + MAJOR_CITIES
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
