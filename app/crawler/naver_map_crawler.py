import os
import asyncio
import logging
import random
import time
import json
import base64
import re
from typing import Any, List, Dict, Optional
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
    MAX_PAGES = int(os.getenv("CRAWLER_MAX_PAGES", "5"))
    RATE_LIMIT_RETRIES = int(os.getenv("CRAWLER_RATE_LIMIT_RETRIES", "3"))
    RATE_LIMIT_BACKOFF_SEC = float(os.getenv("CRAWLER_RATE_LIMIT_BACKOFF_SEC", "2.0"))
    PAGE_WAIT_JITTER_MS = int(os.getenv("CRAWLER_PAGE_WAIT_JITTER_MS", "800"))
    # 정보 탭 클릭 후 Apollo state/DOM이 안정화될 때까지 기다리는 시간(운영 중 튜닝 가능).
    INFO_TAB_RENDER_WAIT_MS = int(os.getenv("CRAWLER_INFO_TAB_RENDER_WAIT_MS", "2000"))
    PHONE_REVEAL_TIMEOUT_SEC = float(os.getenv("CRAWLER_PHONE_REVEAL_TIMEOUT_SEC", "30"))
    STORAGE_STATE_PATH_ENV = "NAVER_STORAGE_STATE_PATH"
    INFO_TAB_LABEL = "정보"
    REPRESENTATIVE_KEYWORDS_LABEL = "대표 키워드"
    PHONE_VIEW_LABEL = "전화번호 보기"
    PHONE_PATTERN = re.compile(
        r"(?<!\d)(?:0507[\s\-]?\d{3,4}[\s\-]?\d{4}|(?:\+82[\s\-]?)?0\d{1,2}[\s\-]?\d{3,4}[\s\-]?\d{4}|(?:1544|1566|1577|1588|1599|1600|1644|1661|1670|1688)[\s\-]?\d{4})(?!\d)"
    )
    
    def __init__(self, headless: bool = True):
        self.headless = headless
        self.storage_state_path = os.getenv(self.STORAGE_STATE_PATH_ENV)
        self._executor = ThreadPoolExecutor(max_workers=1)

    def _get_executor(self) -> ThreadPoolExecutor:
        """왜: close() 이후 재사용 호출에서도 안정적으로 단일 executor를 보장하기 위함.
        사용처: search_rehearsal_rooms/reveal_phone_number/reveal_representative_keywords에서
        run_in_executor 호출 직전에 가져와 thread 실행 컨텍스트를 일관되게 유지한다.
        """
        if self._executor is None:
            self._executor = ThreadPoolExecutor(max_workers=1)
        return self._executor

    def close(self) -> None:
        """왜: crawler 수명 종료 시 executor thread를 명시적으로 정리해 누수를 방지하기 위함.
        사용처: 스크립트 종료 finally 블록 또는 서비스 종료 훅에서 호출한다.
        """
        executor = self._executor
        if executor is None:
            return
        self._executor = None
        try:
            executor.shutdown(wait=False, cancel_futures=True)
        except TypeError:
            executor.shutdown(wait=False)

    def __del__(self):
        try:
            self.close()
        except Exception:
            return

    async def search_rehearsal_rooms(self, query: str = "합주실") -> List[Dict[str, str]]:
        """Search rehearsal rooms by keyword and return parsed item summaries.

        Args:
            query: Search phrase for Naver Map (for example, "sadang rehearsal room").

        Returns:
            List of dictionaries containing id, name, and address fields.
        """
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(self._get_executor(), self._search_sync, query)

    async def reveal_phone_number(self, place_id: str) -> Optional[str]:
        """Reveal phone number from place page (visible text or click-to-reveal flow)."""
        if not place_id:
            return None
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(self._get_executor(), self._reveal_phone_sync, str(place_id))

    async def reveal_representative_keywords(self, place_id: str) -> List[str]:
        """장소 상세 페이지(정보 탭)에서 대표 키워드를 추출한다."""
        if not place_id:
            return []
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            self._get_executor(),
            self._reveal_representative_keywords_sync,
            str(place_id),
        )

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
        deadline = time.monotonic() + max(self.PHONE_REVEAL_TIMEOUT_SEC, 5.0)

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
                if time.monotonic() >= deadline:
                    return revealed_from_api
                page.goto(entry_url)
                page.wait_for_load_state("domcontentloaded")
                initial_wait_ms = min(
                    self._wait_with_jitter(self.PAGE_WAIT_MS),
                    max(0, int((deadline - time.monotonic()) * 1000)),
                )
                if initial_wait_ms > 0:
                    page.wait_for_timeout(initial_wait_ms)

                target_frame = None
                for frame in page.frames:
                    if frame.url and f"pcmap.place.naver.com/place/{place_id}" in frame.url:
                        target_frame = frame
                        break
                if not target_frame:
                    return revealed_from_api

                body_timeout_ms = min(5000, max(800, int((deadline - time.monotonic()) * 1000)))
                body_text = target_frame.locator("body").inner_text(timeout=body_timeout_ms)
                immediate_phone = self._extract_phone_candidate(body_text)
                if immediate_phone:
                    return immediate_phone

                if self.PHONE_VIEW_LABEL not in body_text:
                    return revealed_from_api

                clicked = False
                try:
                    click_timeout_ms = min(3000, max(800, int((deadline - time.monotonic()) * 1000)))
                    target_frame.get_by_text(self.PHONE_VIEW_LABEL, exact=False).first.click(
                        timeout=click_timeout_ms,
                        force=True,
                    )
                    clicked = True
                except Exception:
                    try:
                        result = target_frame.evaluate(
                            """(needle) => {
                                const nodes = [...document.querySelectorAll('*')];
                                const el = nodes.find((n) => n.textContent && n.textContent.includes(needle));
                                if (!el) return 'not-found';
                                const clickable = el.closest('button, [role="button"], a, [onclick]');
                                if (clickable) {
                                    try { clickable.click(); return 'clicked-via-js'; } catch (e) {}
                                }
                                try { el.click(); return 'clicked-via-js'; } catch (e) {}
                                return 'not-clicked';
                            }""",
                            self.PHONE_VIEW_LABEL,
                        )
                        clicked = str(result).startswith("clicked")
                    except Exception:
                        clicked = False

                if clicked:
                    post_click_wait_ms = min(
                        self._wait_with_jitter(3000),
                        max(0, int((deadline - time.monotonic()) * 1000)),
                    )
                    if post_click_wait_ms > 0:
                        page.wait_for_timeout(post_click_wait_ms)
                    if revealed_from_api:
                        return revealed_from_api
                    after_timeout_ms = min(5000, max(800, int((deadline - time.monotonic()) * 1000)))
                    after_text = target_frame.locator("body").inner_text(timeout=after_timeout_ms)
                    revealed_phone = self._extract_phone_candidate(after_text)
                    if revealed_phone:
                        return revealed_phone
                return revealed_from_api
            except Exception as e:
                logger.warning("Failed to reveal phone number for place_id=%s: %s", place_id, e)
                return revealed_from_api
            finally:
                browser.close()

    def _reveal_representative_keywords_sync(self, place_id: str) -> List[str]:
        """장소 상세 페이지에서 대표 키워드를 직접 추출한다."""
        user_agent_str = self._resolve_user_agent()
        entry_url = f"https://map.naver.com/p/entry/place/{place_id}"

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
                logger.warning(f"Failed to launch Chrome channel for keyword reveal: {e}. Falling back.")
                try:
                    browser = p.chromium.launch(
                        headless=self.headless,
                        args=[
                            "--disable-blink-features=AutomationControlled",
                            "--no-sandbox",
                        ],
                    )
                except Exception as e2:
                    logger.error(f"Failed to launch browser for keyword reveal: {e2}")
                    return []

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
                    return []

                self._open_info_tab(target_frame)
                page.wait_for_timeout(self._wait_with_jitter(self.INFO_TAB_RENDER_WAIT_MS))

                apollo_keywords: List[str] = []
                try:
                    raw = target_frame.evaluate(
                        """() => {
                            const state = window.__APOLLO_STATE__;
                            if (!state || typeof state !== 'object') return [];
                            const out = [];
                            const seen = new Set();
                            const keyMatched = (k) => /keyword|hashtag|tag|키워드|해시태그|태그/i.test(String(k || ""));
                            const push = (v) => {
                                if (typeof v !== 'string') return;
                                const t = v.trim();
                                if (!t || seen.has(t)) return;
                                seen.add(t);
                                out.push(t);
                            };
                            const walk = (obj, depth = 0, key = "") => {
                                if (depth > 6 || obj == null) return;
                                if (typeof obj === 'string') {
                                    if (keyMatched(key)) push(obj);
                                    return;
                                }
                                if (Array.isArray(obj)) {
                                    for (const item of obj) walk(item, depth + 1, key);
                                    return;
                                }
                                if (typeof obj === 'object') {
                                    for (const [k, v] of Object.entries(obj)) {
                                        walk(v, depth + 1, k);
                                    }
                                }
                            };
                            walk(state);
                            return out.slice(0, 40);
                        }"""
                    )
                    if isinstance(raw, list):
                        apollo_keywords = [str(x).strip() for x in raw if isinstance(x, str) and str(x).strip()]
                except Exception:
                    apollo_keywords = []

                text_keywords: List[str] = []
                try:
                    body_text = target_frame.locator("body").inner_text(timeout=5000)
                    text_keywords = self._extract_representative_keywords_from_text(body_text)
                except Exception:
                    text_keywords = []

                return self._normalize_representative_keywords(apollo_keywords + text_keywords)
            except Exception as e:
                logger.warning("Failed to reveal representative keywords for place_id=%s: %s", place_id, e)
                return []
            finally:
                browser.close()

    def _open_info_tab(self, target_frame) -> None:
        """정보 탭 클릭을 시도한다. 실패해도 다음 추출 로직은 계속 진행한다."""
        try:
            target_frame.get_by_text(self.INFO_TAB_LABEL, exact=False).first.click(timeout=2500, force=True)
            return
        except Exception:
            pass

        try:
            target_frame.evaluate(
                """(label) => {
                    const nodes = [...document.querySelectorAll('*')];
                    const el = nodes.find((n) => n.textContent && n.textContent.trim() === label);
                    if (el) { try { el.click(); } catch (e) {} }
                }""",
                self.INFO_TAB_LABEL,
            )
        except Exception:
            return

    @classmethod
    def _extract_representative_keywords_from_text(cls, text: str) -> List[str]:
        """본문 텍스트에서 '대표 키워드' 섹션의 키워드를 추출한다."""
        if not text:
            return []

        marker_idx = text.find(cls.REPRESENTATIVE_KEYWORDS_LABEL)
        if marker_idx < 0:
            return []

        tail = text[marker_idx + len(cls.REPRESENTATIVE_KEYWORDS_LABEL):]
        lines = [ln.strip() for ln in tail.splitlines()]
        candidates: List[str] = []
        section_break_markers = {
            "이용안내",
            "안내",
            "소개",
            "메뉴",
            "가격",
            "찾아오시는 길",
            "편의",
        }

        for line in lines:
            if not line:
                continue

            if line in section_break_markers and candidates:
                break

            if line in {"홈", "소식", "예약", "리뷰", "사진", "정보", "문의", cls.REPRESENTATIVE_KEYWORDS_LABEL}:
                continue

            parts = re.split(r"\s{2,}|,|/|\|", line)
            for part in parts:
                token = part.strip("[](){}-•· ")
                if not token:
                    continue
                if len(token) > 20:
                    continue
                if re.search(r"\d{2,}", token):
                    continue
                if "http" in token.lower():
                    continue
                candidates.append(token)

            if len(candidates) >= 12:
                break

        return cls._normalize_representative_keywords(candidates)

    @staticmethod
    def _normalize_representative_keywords(values: List[str]) -> List[str]:
        """대표 키워드 리스트를 공백/중복 정리한다."""
        cleaned: List[str] = []
        seen: set[str] = set()
        for value in values:
            if not isinstance(value, str):
                continue
            token = re.sub(r"\s+", " ", value).strip()
            if not token:
                continue
            lowered = token.lower()
            if lowered in seen:
                continue
            seen.add(lowered)
            cleaned.append(token)
        return cleaned[:20]

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
        raw = payload.strip()
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
                const mergeNonNull = (target, source) => {
                    if (!source) return;
                    for (const [k, v] of Object.entries(source)) {
                        if (v !== null && v !== undefined) {
                            target[k] = v;
                        }
                    }
                };
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
                        mergeNonNull(place, details[pid]);
                    }
                    // If bookingBusinessId exists, merge BookingBusiness data
                    if (place.id && bookings[place.id]) {
                        mergeNonNull(place, bookings[place.id]);
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
                logger.info(f"??Finished {query}: Found {len(region_results)} rooms")
                
                for item in region_results:
                    if item["id"] not in all_results:
                        all_results[item["id"]] = item
                        
                # Small randomized delay between regions to reduce burst patterns
                await asyncio.sleep(2 + random.uniform(0, 1.5))
                
            except Exception as e:
                logger.error(f"??Failed to crawl {query}: {e}")
            
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


