import os
import httpx
import logging
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

class NaverRoomFetcher:
    """네이버 예약 GraphQL API를 통해 합주실 상세 정보를 수집합니다."""
    
    GRAPHQL_URL = "https://booking.naver.com/graphql"
    HEADERS = {
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }
    
    # Configurable timeout via environment variable
    REQUEST_TIMEOUT = float(os.getenv("FETCHER_TIMEOUT", "10.0"))
    
    async def fetch_full_info(self, business_id: str) -> Optional[Dict]:
        """
        비즈니스 ID에 해당하는 합주실의 전체 정보(기본정보, 룸목록, 지하철)를 수집합니다.
        
        Returns:
            Dict: {
                "business": {...},
                "rooms": [...],
                "subway": {...}
            } or None if failed
        """
        async with httpx.AsyncClient() as client:
            try:
                # 1. 지점 정보 (Business)
                business_info = await self._fetch_business(client, business_id)
                if not business_info:
                    logger.warning(f"Failed to fetch business info for {business_id}")
                    return None
                
                # 2. 룸 목록 (BizItems)
                rooms = await self._fetch_biz_items(client, business_id)
                
                # 3. 지하철 정보 (NearSubway) - 좌표가 있는 경우만
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

    async def _fetch_business(self, client: httpx.AsyncClient, business_id: str) -> Optional[Dict]:
        query = """
        query business($businessId: String!) {
            business(input: {businessId: $businessId}) {
                id
                businessId
                name
                businessDisplayName
                coordinates
                placeId
            }
        }
        """
        payload = {
            "operationName": "business",
            "variables": {"businessId": business_id},
            "query": query
        }

        resp = await client.post(self.GRAPHQL_URL, json=payload, headers=self.HEADERS, timeout=10.0)
        if resp.status_code != 200:
            logger.error(f"Business Error: {resp.status_code}, Body: {resp.text}")
        resp.raise_for_status()
        data = resp.json()
        business = data.get("data", {}).get("business")

        # coordinates는 [longitude, latitude] 배열로 반환됨 -> 객체로 변환
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
            desc
            minMaxPrice {
              minPrice
              maxNormalPrice
            }
            bizItemResources {
              resourceUrl
            }
            bookingTimeUnitCode
            minBookingTime
          }
        }
        """
        payload = {
            "operationName": "bizItems",
            "variables": {
                "input": {
                    "businessId": business_id,
                    "lang": "ko",
                    "projections": "MIN_MAX_PRICE,RESOURCE" # 필수: 가격, 이미지 포함
                }
            },
            "query": query
        }
        
        resp = await client.post(self.GRAPHQL_URL, json=payload, headers=self.HEADERS, timeout=10.0)
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
        # placeId가 없으면 임의값이라도 넣어야 하는 경우가 있음 (일단 None 허용)
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
            resp = await client.post(self.GRAPHQL_URL, json=payload, headers=self.HEADERS, timeout=5.0)
            if resp.status_code != 200:
                return None
            data = resp.json()
            return data.get("data", {}).get("nearSubway")
        except Exception:
            return None

# 테스트 코드
if __name__ == "__main__":
    import asyncio
    logging.basicConfig(level=logging.INFO)
    
    async def main():
        fetcher = NaverRoomFetcher()
        # 비쥬합주실 1호점 테스트
        info = await fetcher.fetch_full_info("522011")
        print(f"Business: {info['business']['businessDisplayName']}")
        print(f"Room count: {len(info['rooms'])}")
        if info['subway']:
            print(f"Subway: {info['subway']['displayName']}")

    asyncio.run(main())
