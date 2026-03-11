import logging
import os
import random
import asyncio
import json
import re
import httpx
from typing import Any, Dict, List, Optional
from app.core.name_utils import normalize_name_token

logger = logging.getLogger(__name__)

class NaverRoomFetcher:
    """네이버 예약 GraphQL API를 통해 합주실 상세 정보를 수집하는 fetcher."""
    
    GRAPHQL_URL = "https://booking.naver.com/graphql"
    HEADERS = {
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }
    
    # 환경변수로 설정 가능한 타임아웃/재시도 파라미터
    REQUEST_TIMEOUT = float(os.getenv("FETCHER_TIMEOUT", "10.0"))
    RATE_LIMIT_RETRIES = int(os.getenv("FETCHER_RATE_LIMIT_RETRIES", "3"))
    RATE_LIMIT_BACKOFF_SEC = float(os.getenv("FETCHER_RATE_LIMIT_BACKOFF_SEC", "1.2"))
    RATE_LIMIT_JITTER_SEC = float(os.getenv("FETCHER_RATE_LIMIT_JITTER_SEC", "0.6"))
    STORAGE_STATE_PATH_ENV = "NAVER_STORAGE_STATE_PATH"

    def __init__(self):
        """환경변수에서 쿠키 헤더 또는 storage state를 로드하여 인증 헤더를 초기화한다."""
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
        """지정 business ID의 전체 합주실 정보(업체·방·인근 지하철)를 수집한다.

        Args:
            business_id (str): 네이버 예약 business ID.
            source_hint (Optional[Dict[str, Any]]): business 조회 실패 시
                fallback 이름으로 사용할 힌트 정보.

        Returns:
            Optional[Dict]: ``{"business": {...}, "rooms": [...], "subway": {...}}``
            형태의 딕셔너리. 실패 시 None.
        """
        async with httpx.AsyncClient() as client:
            try:
                # 1) Business-level info (best-effort)
                business_info = None
                try:
                    business_info = await self._fetch_business(client, business_id)
                except Exception as e:
                    logger.warning(
                        "Business query failed; continuing with room-based fallback: business_id=%s err=%s",
                        business_id,
                        e,
                    )
                 
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
                        rooms=rooms,
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
        rooms: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict:
        """business 조회 실패 시 source_hint와 룸 이름을 활용해 대체 업체 정보를 생성한다."""
        room_name_tokens = {
            normalize_name_token((room or {}).get("name"))
            for room in (rooms or [])
            if isinstance(room, dict)
        }
        room_name_tokens.discard("")

        hint_name = (source_hint or {}).get("name")
        fallback_name = f"business-{business_id}"
        if isinstance(hint_name, str) and hint_name.strip():
            normalized_hint = normalize_name_token(hint_name)
            if normalized_hint and normalized_hint not in room_name_tokens:
                fallback_name = hint_name.strip()
            else:
                logger.warning(
                    "Fallback business name rejected due to room-name collision: business_id=%s hint_name=%s",
                    business_id,
                    hint_name,
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
        """네이버 business GraphQL 쿼리로 업체 기본 정보를 조회한다."""
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
        """네이버 bizItems GraphQL 쿼리로 업체의 룸(BizItem) 목록을 조회한다."""
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
        """좌표 기반으로 인근 지하철역 정보를 조회한다."""
        # 일부 케이스에서 placeId 형태의 입력을 기대함. 빈 문자열 fallback 허용.
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
        """GraphQL 페이로드를 전송하고, 429 Rate Limit 및 일시적 오류 시 재시도한다."""
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
        """지수 백오프 + 지터를 적용하여 재시도 대기 시간을 계산한다."""
        backoff = self.RATE_LIMIT_BACKOFF_SEC * (2 ** attempt)
        jitter = random.uniform(0.0, max(self.RATE_LIMIT_JITTER_SEC, 0.0))
        return backoff + jitter

    def _load_cookie_header_from_storage_state(self, path: Optional[str]) -> Optional[str]:
        """storage state JSON에서 네이버 도메인 쿠키를 추출하여 Cookie 헤더 문자열을 생성한다."""
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
        """주어진 도메인이 네이버 쿠키 허용 도메인인지 판별한다."""
        normalized = str(domain or "").strip().lstrip(".").lower()
        return normalized == "naver.com" or normalized.endswith(".naver.com")

# 수동 동작 테스트
if __name__ == "__main__":
    import asyncio
    logging.basicConfig(level=logging.INFO)
    
    async def main():
        """네이버 룸 페처 동작을 테스트한다."""
        fetcher = NaverRoomFetcher()
        # 샘플 business 테스트 실행
        info = await fetcher.fetch_full_info("522011")
        print(f"Business: {info['business']['businessDisplayName']}")
        print(f"Room count: {len(info['rooms'])}")
        if info['subway']:
            print(f"Subway: {info['subway']['displayName']}")

    asyncio.run(main())
