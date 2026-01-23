import asyncio
import logging
from typing import List, Dict, Optional
from playwright.async_api import async_playwright

logger = logging.getLogger(__name__)

class NaverMapCrawler:
    """네이버 지도에서 합주실을 검색하고 Business ID를 수집합니다."""
    
    BASE_URL = "https://pcmap.place.naver.com/place/list"
    
    def __init__(self, headless: bool = True):
        self.headless = headless

    async def search_rehearsal_rooms(self, query: str = "합주실") -> List[Dict[str, str]]:
        """
        특정 키워드로 합주실을 검색하고 결과 목록을 반환합니다.
        
        Args:
            query (str): 검색 키워드 (예: "홍대 합주실")
            
        Returns:
            List[Dict]: [{'id': 'business_id', 'name': '지점명', 'category': '카테고리'}, ...]
        """
        results = {}
        
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=self.headless)
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            )
            page = await context.new_page()
            
            try:
                # 1. 첫 페이지 이동
                url = f"{self.BASE_URL}?query={query}&display=70"
                logger.info(f"Searching: {query} -> {url}")
                await page.goto(url)
                await page.wait_for_load_state("networkidle")
                
                # 2. 첫 페이지 데이터 추출
                initial_data = await self._extract_apollo_state(page)
                self._merge_results(results, initial_data)
                
                # 3. 페이지네이션 처리
                # 네이버 지도는 하단에 1, 2, 3.. 페이지 버튼이 있음
                # 하지만 정확한 총 페이지 수를 알기 어려우므로, 
                # '다음' 버튼이 있거나 다음 숫자가 있을 때까지 반복 클릭
                
                # 현재는 안전하게 최대 5페이지만 탐색 (대부분 지역 검색은 1~2페이지)
                for i in range(2, 6):
                    # 페이지 번호 버튼 찾기 (예: text="2")
                    # 주의: 네이버 지도 UI 구조상 명시적인 버튼 selector가 까다로움.
                    # 여기서는 간단히 다음 페이지 클릭 시도만 구현
                    next_btn = page.get_by_role("link", name=str(i), exact=True)
                    
                    if await next_btn.is_visible():
                        logger.info(f"Navigating to page {i}")
                        await next_btn.click()
                        await page.wait_for_timeout(1000) # 데이터 로딩 대기
                        await page.wait_for_load_state("networkidle")
                        
                        page_data = await self._extract_apollo_state(page)
                        if not page_data:
                            break
                        self._merge_results(results, page_data)
                    else:
                        break
                        
            except Exception as e:
                logger.error(f"Error crawling {query}: {e}")
            finally:
                await browser.close()
                
        return list(results.values())

    async def _extract_apollo_state(self, page) -> List[Dict]:
        """window.__APOLLO_STATE__ 변수에서 PlaceSummary 데이터 추출"""
        return await page.evaluate("""
            () => {
                const state = window.__APOLLO_STATE__;
                if (!state) return [];
                
                const places = [];
                for (const key in state) {
                    // key format: "PlaceSummary:123456"
                    if (key.startsWith('PlaceSummary:')) {
                        const place = state[key];
                        places.push({
                            id: key.split(':')[1],
                            name: place.name,
                            category: place.category,
                            address: place.address,
                            roadAddress: place.roadAddress,
                            x: place.x,
                            y: place.y
                        });
                    }
                }
                return places;
            }
        """)

    def _merge_results(self, target: Dict, source: List[Dict]):
        """중복 제거하며 결과 병합"""
        for item in source:
            if item["id"] not in target:
                target[item["id"]] = item

    async def crawl_major_regions(self) -> List[Dict]:
        """주요 지역별 검색 수행"""
        regions = [
            "서울 합주실", "경기 합주실", "홍대 합주실", "강남 합주실", "사당 합주실",
            "건대 합주실", "신촌 합주실", "부산 합주실", "대구 합주실"
        ]
        
        all_results = {}
        
        # 순차 실행 (브라우저 리소스 고려)
        for query in regions:
            logger.info(f"Starting crawl for region: {query}")
            region_results = await self.search_rehearsal_rooms(query)
            logger.info(f"Found {len(region_results)} rooms in {query}")
            
            for item in region_results:
                all_results[item["id"]] = item
                
            # Rate limit 회피용 딜레이
            await asyncio.sleep(2)
            
        return list(all_results.values())

# 수동 실행용
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    crawler = NaverMapCrawler(headless=False)
    results = asyncio.run(crawler.search_rehearsal_rooms("사당 합주실"))
    print(f"Total found: {len(results)}")
    for r in results[:5]:
        print(r)
