import os
import asyncio
import logging
import random
import time
from typing import List, Dict, Optional
from playwright.sync_api import sync_playwright
from concurrent.futures import ThreadPoolExecutor
from app.core.constants import PRIORITY_AREA_QUERIES
from fake_useragent import UserAgent

logger = logging.getLogger(__name__)

class NaverMapCrawler:
    """Search Naver Map for rehearsal rooms and collect business IDs.

    Main behavior:
    - Launch sync Playwright in a background thread for stable Windows runtime.
    - Parse window.__APOLLO_STATE__ to extract place/business objects.
    """
    
    BASE_URL = "https://pcmap.place.naver.com/place/list"
    
    # Configurable timeouts via environment variables
    PAGE_WAIT_MS = int(os.getenv("CRAWLER_PAGE_WAIT_MS", "3000"))
    SCROLL_WAIT_MS = int(os.getenv("CRAWLER_SCROLL_WAIT_MS", "1500"))
    MAX_PAGES = int(os.getenv("CRAWLER_MAX_PAGES", "5"))
    RATE_LIMIT_RETRIES = int(os.getenv("CRAWLER_RATE_LIMIT_RETRIES", "3"))
    RATE_LIMIT_BACKOFF_SEC = float(os.getenv("CRAWLER_RATE_LIMIT_BACKOFF_SEC", "2.0"))
    PAGE_WAIT_JITTER_MS = int(os.getenv("CRAWLER_PAGE_WAIT_JITTER_MS", "800"))
    STORAGE_STATE_PATH_ENV = "NAVER_STORAGE_STATE_PATH"
    
    def __init__(self, headless: bool = True):
        self.headless = headless
        self.storage_state_path = os.getenv(self.STORAGE_STATE_PATH_ENV)
        self._executor = ThreadPoolExecutor(max_workers=1)

    async def search_rehearsal_rooms(self, query: str = "합주실") -> List[Dict[str, str]]:
        """Search rehearsal rooms by keyword and return parsed item summaries.

        Args:
            query: Search phrase for Naver Map (for example, "sadang rehearsal room").

        Returns:
            List of dictionaries containing id, name, and address fields.
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

            context_kwargs = {
                "user_agent": user_agent_str,
                "extra_http_headers": {"Referer": "https://map.naver.com/"},
                "viewport": {"width": 1920, "height": 1080},
                "locale": "ko-KR",
                "timezone_id": "Asia/Seoul",
            }
            if self.storage_state_path:
                if os.path.exists(self.storage_state_path):
                    context_kwargs["storage_state"] = self.storage_state_path
                    logger.info(
                        "Using NAVER_STORAGE_STATE_PATH for map crawl context: %s",
                        self.storage_state_path,
                    )
                else:
                    logger.warning(
                        "NAVER_STORAGE_STATE_PATH is set but file not found: %s",
                        self.storage_state_path,
                    )

            context = browser.new_context(**context_kwargs)
            
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
                # 1) Navigate to the first result page
                url = f"{self.BASE_URL}?query={query}&display=70"
                logger.info(f"Searching: {query} -> {url}")
                if not self._goto_search_page_with_retry(page, url):
                    logger.warning(f"Failed to load search page after retries: {query}")
                    return []
                
                # 2) Extract first-page data
                initial_data = self._extract_apollo_state_sync(page)
                self._merge_results(results, initial_data)
                
                # 3) Handle pagination (up to MAX_PAGES)
                for i in range(2, self.MAX_PAGES + 1):
                    next_btn = page.get_by_role("link", name=str(i), exact=True)
                    
                    if next_btn.is_visible():
                        logger.info(f"Navigating to page {i}")
                        next_btn.click()
                        page.wait_for_timeout(self._wait_with_jitter(1000))
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

    def _wait_with_jitter(self, base_ms: int) -> int:
        return max(0, int(base_ms + random.randint(0, self.PAGE_WAIT_JITTER_MS)))

    def _goto_search_page_with_retry(self, page, url: str) -> bool:
        max_attempts = self.RATE_LIMIT_RETRIES + 1

        for attempt in range(max_attempts):
            response = page.goto(url)
            status = getattr(response, "status", None)

            if status == 429:
                backoff = self.RATE_LIMIT_BACKOFF_SEC * (2**attempt)
                jitter = random.uniform(0, max(self.RATE_LIMIT_BACKOFF_SEC, 0.0))
                delay = backoff + jitter
                logger.warning(
                    "Naver map rate limit (429): attempt %s/%s, sleeping %.2fs",
                    attempt + 1,
                    max_attempts,
                    delay,
                )
                time.sleep(delay)
                continue

            page.wait_for_load_state("networkidle")
            page.wait_for_timeout(self._wait_with_jitter(self.PAGE_WAIT_MS))
            return True

        return False

    def _extract_apollo_state_sync(self, page) -> List[Dict]:
        """Extract PlaceSummary and enrichment fields from window.__APOLLO_STATE__ (sync).

        Rationale:
            Collect PlaceDetail (description/hours) and BookingBusiness metadata
            in the same page pass to maximize usable context without extra requests.
            Missing enrichment data does not break baseline behavior.
        """
        return page.evaluate("""
            () => {
                const state = window.__APOLLO_STATE__;
                if (!state) {
                     return ["NO_APOLLO_STATE", "URL:" + window.location.href, "BODY_HIDDEN_FOR_SECURITY"];
                }
                
                const places = [];
                const details = {};    // placeId -> PlaceDetail fields
                const bookings = {};   // placeId -> BookingBusiness fields
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
                
                // Merge PlaceDetail/BookingBusiness into PlaceSummary (enrichment)
                for (const place of places) {
                    const pid = place.placeId;
                    if (pid && details[pid]) {
                        Object.assign(place, details[pid]);
                    }
                    // If bookingBusinessId exists, merge BookingBusiness data
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
        """Merge results while deduplicating by business id."""
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
        Crawl only globally configured priority station areas.
        Sequential execution for stability on Windows.
        Returns list of collected business Item dicts (deduplicated).
        """
        all_queries = list(PRIORITY_AREA_QUERIES)
        logger.info(f"Starting sequential crawl for {len(all_queries)} priority areas...")
        
        all_results = {}

        for idx, query in enumerate(all_queries):
            logger.info(f"[{idx+1}/{len(all_queries)}] Searching: {query}")
            try:
                region_results = await self.search_rehearsal_rooms(query)
                logger.info(f"✅ Finished {query}: Found {len(region_results)} rooms")
                
                for item in region_results:
                    if item["id"] not in all_results:
                        all_results[item["id"]] = item
                        
                # Small randomized delay between regions to reduce burst patterns
                await asyncio.sleep(2 + random.uniform(0, 1.5))
                
            except Exception as e:
                logger.error(f"❌ Failed to crawl {query}: {e}")
            
        logger.info(f"Total unique businesses found in priority areas: {len(all_results)}")
        return list(all_results.values())

# Manual run helper
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    crawler = NaverMapCrawler(headless=False)
    results = asyncio.run(crawler.search_rehearsal_rooms("사당 합주실"))
    print(f"Total found: {len(results)}")
    for r in results[:5]:
        print(r)
