import logging
import os
import random
import asyncio
import json
import httpx
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

class NaverRoomFetcher:
    """Collect rehearsal-room details via Naver Booking GraphQL API."""
    
    GRAPHQL_URL = "https://booking.naver.com/graphql"
    HEADERS = {
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }
    
    # Configurable timeout via environment variable
    REQUEST_TIMEOUT = float(os.getenv("FETCHER_TIMEOUT", "10.0"))
    RATE_LIMIT_RETRIES = int(os.getenv("FETCHER_RATE_LIMIT_RETRIES", "3"))
    RATE_LIMIT_BACKOFF_SEC = float(os.getenv("FETCHER_RATE_LIMIT_BACKOFF_SEC", "1.2"))
    RATE_LIMIT_JITTER_SEC = float(os.getenv("FETCHER_RATE_LIMIT_JITTER_SEC", "0.6"))
    STORAGE_STATE_PATH_ENV = "NAVER_STORAGE_STATE_PATH"

    def __init__(self):
        self.headers = dict(self.HEADERS)

        cookie_header = os.getenv("NAVER_COOKIE_HEADER")
        if cookie_header:
            self.headers["Cookie"] = cookie_header
            logger.info("Using NAVER_COOKIE_HEADER for GraphQL requests")
            return

        storage_state_path = os.getenv(self.STORAGE_STATE_PATH_ENV)
        cookie_from_state = self._load_cookie_header_from_storage_state(storage_state_path)
        if cookie_from_state:
            self.headers["Cookie"] = cookie_from_state
            logger.info("Using NAVER_STORAGE_STATE_PATH cookies for GraphQL requests")
    
    async def fetch_full_info(
        self,
        business_id: str,
        source_hint: Optional[Dict[str, Any]] = None,
    ) -> Optional[Dict]:
        """
        Fetch full room info for a business ID (business, rooms, nearby subway).
        
        Returns:
            Dict: {
                "business": {...},
                "rooms": [...],
                "subway": {...}
            } or None if failed
        """
        async with httpx.AsyncClient() as client:
            try:
                # 1) Business-level info
                business_info = await self._fetch_business(client, business_id)
                
                # 2) Room list (BizItems)
                rooms = await self._fetch_biz_items(client, business_id)

                # 보수적 운영 규칙:
                # business 정보가 비어도 rooms가 있으면 수집/파싱을 계속한다.
                # (예약 불가 단정 대신 '정보 부족/문의 필요'로 해석)
                if not business_info:
                    if not rooms:
                        logger.warning(f"Failed to fetch business info for {business_id}")
                        return None
                    logger.warning(
                        "Business query returned null; using fallback business payload for %s",
                        business_id,
                    )
                    business_info = self._build_business_fallback(
                        business_id,
                        source_hint=source_hint,
                    )
                
                # 3) Nearby subway info (only when coordinates are available)
                subway = None
                coord = business_info.get("coordinates")
                if coord:
                    subway = await self._fetch_near_subway(
                        client, 
                        coord["latitude"], 
                        coord["longitude"],
                        business_info.get("placeId")
                    )
                
                return {
                    "business": business_info,
                    "rooms": rooms,
                    "subway": subway
                }
                
            except Exception as e:
                logger.error(f"Error fetching full info for {business_id}: {e}")
                return None

    @staticmethod
    def _build_business_fallback(
        business_id: str,
        source_hint: Optional[Dict[str, Any]] = None,
    ) -> Dict:
        hint_name = (source_hint or {}).get("name")
        fallback_name = (
            hint_name.strip()
            if isinstance(hint_name, str) and hint_name.strip()
            else f"business-{business_id}"
        )
        return {
            "id": business_id,
            "businessId": business_id,
            "name": fallback_name,
            "businessDisplayName": fallback_name,
            "businessCategory": None,
            "bookingUrl": None,
            "bookingGuideJson": None,
            "businessResources": None,
            "desc": "",
            "coordinates": None,
            "placeId": None,
            "addressJson": None,
            "phoneInformationJson": None,
            "placeScheduleJson": None,
            "extraDescJson": None,
            "additionalPropertyJson": None,
            "eventDescJson": None,
        }

    async def _fetch_business(self, client: httpx.AsyncClient, business_id: str) -> Optional[Dict]:
        query = """
        query business($businessId: String!) {
            business(input: {businessId: $businessId}) {
                id
                businessId
                name
                businessDisplayName
                businessCategory
                bookingUrl
                bookingGuideJson
                desc
                coordinates
                placeId
                addressJson
                phoneInformationJson
                placeScheduleJson
                extraDescJson
                additionalPropertyJson
                eventDescJson
                businessResources {
                    resourceTypeCode
                    resourceUrl
                    order
                }
            }
        }
        """
        payload = {
            "operationName": "business",
            "variables": {"businessId": business_id},
            "query": query
        }

        resp = await self._post_graphql(client, payload, operation_name="business")
        if resp.status_code != 200:
            logger.error(f"Business Error: {resp.status_code}, Body: {resp.text}")
        resp.raise_for_status()
        data = resp.json()
        business = data.get("data", {}).get("business")

        # coordinates come as [longitude, latitude] array -> convert to object
        if business and business.get("coordinates"):
            coords = business["coordinates"]
            if isinstance(coords, list) and len(coords) >= 2:
                business["coordinates"] = {
                    "longitude": coords[0],
                    "latitude": coords[1]
                }

        return business

    async def _fetch_biz_items(self, client: httpx.AsyncClient, business_id: str) -> List[Dict]:
        query = """
        query bizItems($input: BizItemsParams) {
          bizItems(input: $input) {
            bizItemId
            name
            phone
            desc
            stock
            price
            minBookingCount
            maxBookingCount
            bookingTimeUnitCode
            minBookingTime
            maxBookingTime
            isOnsitePayment
            bookingCountSettingJson
            bookingPrecautionJson {
              title
              desc
            }
            extraFeeSettingJson
            extraDescJson
            minMaxPrice {
              minPrice
              maxNormalPrice
            }
            bizItemResources {
              resourceUrl
            }
          }
        }
        """
        payload = {
            "operationName": "bizItems",
            "variables": {
                "input": {
                    "businessId": business_id,
                    "lang": "ko",
                    "projections": "MIN_MAX_PRICE,RESOURCE"  # required: include price/images
                }
            },
            "query": query
        }
        
        resp = await self._post_graphql(client, payload, operation_name="bizItems")
        if resp.status_code != 200:
            logger.error(f"BizItems Error: {resp.status_code}, Body: {resp.text}")
        resp.raise_for_status()
        data = resp.json()
        return data.get("data", {}).get("bizItems") or []

    async def _fetch_near_subway(
        self, 
        client: httpx.AsyncClient, 
        lat: float, 
        lng: float, 
        place_id: Optional[str] = None
    ) -> Optional[Dict]:
        # Some cases still expect placeId-like input; empty string fallback is acceptable.
        query = """
        query nearSubway($input: NearSubwayInput) {
            nearSubway(input: $input) {
                name
                displayName
                nearestExitNo
                walkingDistance
                subwayDetails {
                    color
                    iconName
                }
            }
        }
        """
        payload = {
            "operationName": "nearSubway",
            "variables": {
                "input": {
                    "lang": "ko",
                    "latitude": lat,
                    "longitude": lng,
                    "placeId": place_id or "" 
                }
            },
            "query": query
        }
        
        try:
            resp = await self._post_graphql(client, payload, operation_name="nearSubway")
            if resp.status_code != 200:
                return None
            data = resp.json()
            return data.get("data", {}).get("nearSubway")
        except Exception:
            return None

    async def _post_graphql(
        self,
        client: httpx.AsyncClient,
        payload: Dict,
        operation_name: str,
    ) -> httpx.Response:
        """Post GraphQL payload with rate-limit aware retry."""
        max_attempts = self.RATE_LIMIT_RETRIES + 1
        last_response: Optional[httpx.Response] = None

        for attempt in range(max_attempts):
            try:
                response = await client.post(
                    self.GRAPHQL_URL,
                    json=payload,
                    headers=self.headers,
                    timeout=self.REQUEST_TIMEOUT,
                )
                last_response = response

                if response.status_code != 429:
                    return response

                if attempt < self.RATE_LIMIT_RETRIES:
                    delay = self._compute_backoff_delay(attempt)
                    logger.warning(
                        "GraphQL %s rate-limited (429): attempt %s/%s, sleep %.2fs",
                        operation_name,
                        attempt + 1,
                        max_attempts,
                        delay,
                    )
                    await asyncio.sleep(delay)
                    continue
                return response

            except (httpx.TimeoutException, httpx.TransportError) as exc:
                if attempt < self.RATE_LIMIT_RETRIES:
                    delay = self._compute_backoff_delay(attempt)
                    logger.warning(
                        "GraphQL %s transient error (%s): attempt %s/%s, sleep %.2fs",
                        operation_name,
                        exc.__class__.__name__,
                        attempt + 1,
                        max_attempts,
                        delay,
                    )
                    await asyncio.sleep(delay)
                    continue
                raise

        if last_response is not None:
            return last_response
        raise RuntimeError(f"GraphQL {operation_name} request failed without response")

    def _compute_backoff_delay(self, attempt: int) -> float:
        backoff = self.RATE_LIMIT_BACKOFF_SEC * (2 ** attempt)
        jitter = random.uniform(0.0, max(self.RATE_LIMIT_JITTER_SEC, 0.0))
        return backoff + jitter

    def _load_cookie_header_from_storage_state(self, path: Optional[str]) -> Optional[str]:
        if not path:
            return None
        if not os.path.exists(path):
            logger.warning("NAVER_STORAGE_STATE_PATH file not found: %s", path)
            return None

        try:
            with open(path, "r", encoding="utf-8") as f:
                payload = json.load(f)
        except Exception as exc:
            logger.warning("Failed to read storage state JSON: %s", exc)
            return None

        cookies = payload.get("cookies")
        if not isinstance(cookies, list):
            return None

        pairs: List[str] = []
        for cookie in cookies:
            domain = str(cookie.get("domain", ""))
            name = cookie.get("name")
            value = cookie.get("value")
            if not name or value is None:
                continue
            if self._is_allowed_naver_cookie_domain(domain):
                pairs.append(f"{name}={value}")

        if not pairs:
            return None
        return "; ".join(pairs)

    @staticmethod
    def _is_allowed_naver_cookie_domain(domain: str) -> bool:
        normalized = str(domain or "").strip().lstrip(".").lower()
        return normalized == "naver.com" or normalized.endswith(".naver.com")

# Manual smoke test
if __name__ == "__main__":
    import asyncio
    logging.basicConfig(level=logging.INFO)
    
    async def main():
        fetcher = NaverRoomFetcher()
        # Sample business test run
        info = await fetcher.fetch_full_info("522011")
        print(f"Business: {info['business']['businessDisplayName']}")
        print(f"Room count: {len(info['rooms'])}")
        if info['subway']:
            print(f"Subway: {info['subway']['displayName']}")

    asyncio.run(main())
