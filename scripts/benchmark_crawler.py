
import asyncio
import time
import sys
import os
import logging
from pathlib import Path

# 프로젝트 루트 경로 추가
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.crawler.naver_map_crawler import NaverMapCrawler

# 로깅 설정 (INFO 레벨은 끄고 핵심 결과만 출력)
logging.basicConfig(level=logging.WARNING)

async def benchmark():
    """
    NaverMapCrawler의 검색 성능을 측정합니다.
    동일한 조건(쿼리, 페이지 수 등)에서 실행 시간을 비교합니다.
    """
    crawler = NaverMapCrawler(headless=True)
    
    # 테스트 쿼리 (데이터 양이 적절한 곳 선정)
    queries = ["강남구 합주실", "마포구 합주실"]
    
    print(f"🚀 Benchmarking Crawler Performance...")
    print(f"Target Queries: {queries}")
    
    start_time = time.time()
    total_items = 0
    
    for query in queries:
        q_start = time.time()
        results = await crawler.search_rehearsal_rooms(query)
        q_end = time.time()
        
        count = len(results)
        total_items += count
        print(f"   - '{query}': {count} items found in {q_end - q_start:.2f}s")
        
    end_time = time.time()
    total_duration = end_time - start_time
    
    print(f"\n📊 Benchmark Results")
    print(f"   - Total Duration: {total_duration:.2f}s")
    print(f"   - Total Items: {total_items}")
    print(f"   - Avg Time per Query: {total_duration / len(queries):.2f}s")
    print(f"   - Avg Time per Item: {total_duration / total_items if total_items else 0:.4f}s")

if __name__ == "__main__":
    asyncio.run(benchmark())
