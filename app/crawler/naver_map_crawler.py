import os
import asyncio
import logging
import random
import time
import json
import base64
import re
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
    PHONE_VIEW_LABEL = "전화번호 보기"
    PHONE_PATTERN = re.compile(
        r"(?<!\d)(?:0507[\s\-]?\d{3,4}[\s\-]?\d{4}|(?:\+82[\s\-]?)?0\d{1,2}[\s\-]?\d{3,4}[\s\-]?\d{4}|(?:1544|1566|1577|1588|1599|1600|1644|1661|1670|1688)[\s\-]?\d{4})(?!\d)"
    )
    
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

    async def reveal_phone_number(self, place_id: str) -> Optional[str]:
        """Reveal phone number from place page (visible text or click-to-reveal flow)."""
        if not place_id:
            return None
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(self._executor, self._reveal_phone_sync, str(place_id))

    def _search_sync(self, query: str) -> List[Dict[str, str]]:
        """Synchronous search implementation."""
        user_agent_str = self._resolve_user_agent()

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

    def _reveal_phone_sync(self, place_id: str) -> Optional[str]:
        """Open place entry page and extract/reveal phone number."""
        user_agent_str = self._resolve_user_agent()
        entry_url = f"https://map.naver.com/p/entry/place/{place_id}"
        revealed_from_api: Optional[str] = None

        with sync_playwright() as p:
            browser = None
            try:
                browser = p.chromium.launch(
                    headless=self.headless,
                    channel="chrome",
                    args=[
                        "--disable-blink-features=AutomationControlled",
                        "--no-sandbox",
                    ],
                )
            except Exception as e:
                logger.warning(f"Failed to launch Chrome channel for phone reveal: {e}. Falling back.")
                try:
                    browser = p.chromium.launch(
                        headless=self.headless,
                        args=[
                            "--disable-blink-features=AutomationControlled",
                            "--no-sandbox",
                        ],
                    )
                except Exception as e2:
                    logger.error(f"Failed to launch browser for phone reveal: {e2}")
                    return None

            context_kwargs = {
                "user_agent": user_agent_str,
                "extra_http_headers": {"Referer": "https://map.naver.com/"},
                "viewport": {"width": 430, "height": 920},
                "locale": "ko-KR",
                "timezone_id": "Asia/Seoul",
            }
            if self.storage_state_path and os.path.exists(self.storage_state_path):
                context_kwargs["storage_state"] = self.storage_state_path

            context = browser.new_context(**context_kwargs)

            try:
                from playwright_stealth import stealth_sync

                stealth_sync(context)
            except Exception:
                pass

            context.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
            page = context.new_page()

            def _on_response(response):
                nonlocal revealed_from_api
                try:
                    if "/rest/phone" not in response.url:
                        return
                    payload = response.text().strip()
                    decoded_phone = self._decode_phone_payload(payload)
                    if decoded_phone:
                        revealed_from_api = decoded_phone
                except Exception:
                    return

            page.on("response", _on_response)

            try:
                page.goto(entry_url)
                page.wait_for_load_state("domcontentloaded")
                page.wait_for_timeout(self._wait_with_jitter(self.PAGE_WAIT_MS))

                target_frame = None
                for frame in page.frames:
                    if frame.url and f"pcmap.place.naver.com/place/{place_id}" in frame.url:
                        target_frame = frame
                        break
                if not target_frame:
                    return revealed_from_api

                body_text = target_frame.locator("body").inner_text(timeout=5000)
                immediate_phone = self._extract_phone_candidate(body_text)
                if immediate_phone:
                    return immediate_phone

                if self.PHONE_VIEW_LABEL not in body_text:
                    return revealed_from_api

                clicked = False
                try:
                    target_frame.get_by_text(self.PHONE_VIEW_LABEL, exact=False).first.click(timeout=3000, force=True)
                    clicked = True
                except Exception:
                    try:
                        result = target_frame.evaluate(
                            """(needle) => {
                                const nodes = [...document.querySelectorAll('*')];
                                const el = nodes.find((n) => n.textContent && n.textContent.includes(needle));
                                if (!el) return 'not-found';
                                let cur = el;
                                for (let i = 0; i < 8 && cur; i++) {
                                    try { cur.click(); } catch (e) {}
                                    cur = cur.parentElement;
                                }
                                return 'clicked-via-js';
                            }""",
                            self.PHONE_VIEW_LABEL,
                        )
                        clicked = str(result).startswith("clicked")
                    except Exception:
                        clicked = False

                if clicked:
                    page.wait_for_timeout(self._wait_with_jitter(3000))
                    if revealed_from_api:
                        return revealed_from_api
                    after_text = target_frame.locator("body").inner_text(timeout=5000)
                    revealed_phone = self._extract_phone_candidate(after_text)
                    if revealed_phone:
                        return revealed_phone
                return revealed_from_api
            except Exception as e:
                logger.warning("Failed to reveal phone number for place_id=%s: %s", place_id, e)
                return revealed_from_api
            finally:
                browser.close()

    def _wait_with_jitter(self, base_ms: int) -> int:
        return max(0, int(base_ms + random.randint(0, self.PAGE_WAIT_JITTER_MS)))

    @staticmethod
    def _resolve_user_agent() -> str:
        default = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        try:
            ua = UserAgent(fallback=default)
            return ua.random
        except ImportError:
            logger.warning("fake-useragent not found. Using default user agent.")
            return default
        except Exception as e:
            logger.warning(f"Error generating user agent: {e}. Using default.")
            return default

    @classmethod
    def _extract_phone_candidate(cls, text: str) -> Optional[str]:
        if not text:
            return None
        matches = cls.PHONE_PATTERN.findall(text)
        if not matches:
            return None
        # Prefer first appearance in place panel text.
        return re.sub(r"[.\s]+", "-", str(matches[0])).strip("-")

    @classmethod
    def _decode_phone_payload(cls, payload: str) -> Optional[str]:
        if not payload:
            return None

        # Some endpoints return base64-encoded JSON like {"number":"010-xxxx-xxxx"}.
        for raw in (payload.strip(),):
            try:
                decoded = base64.b64decode(raw).decode("utf-8", errors="ignore")
                parsed = json.loads(decoded)
                if isinstance(parsed, dict):
                    phone = cls._extract_phone_candidate(str(parsed.get("number", "")))
                    if phone:
                        return phone
            except Exception:
                pass

        # Fallback: payload itself may contain JSON/plain phone token.
        try:
            parsed = json.loads(payload)
            if isinstance(parsed, dict):
                phone = cls._extract_phone_candidate(str(parsed.get("number", "")))
                if phone:
                    return phone
        except Exception:
            pass

        return cls._extract_phone_candidate(payload)

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
                            // Enforce booking-business ID only.
                            // Do not fallback to placeId because place-only entries are not reservable.
                            id: place.bookingBusinessId ?? null,
                            bookingBusinessId: place.bookingBusinessId ?? null,
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
            booking_business_id = item.get("bookingBusinessId")
            if not item_id or not booking_business_id:
                logger.info(
                    "Skipping non-bookable map item: name=%s placeId=%s",
                    item.get("name"),
                    item.get("placeId"),
                )
                continue
            item_id = str(item_id)
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
