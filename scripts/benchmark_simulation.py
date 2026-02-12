
import asyncio
import time
import sys
import logging
from pathlib import Path
import random

# 프로젝트 루트 경로 추가
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.crawler.naver_map_crawler import NaverMapCrawler
from app.crawler.naver_room_fetcher import NaverRoomFetcher

# 로깅 설정 (INFO 레벨은 끄고 핵심 결과만 출력)
logging.basicConfig(level=logging.WARNING)

async def benchmark_simulation():
    """
    Discovery Mode vs Full-Fetch Mode 성능 비교 시뮬레이션
    """
    crawler = NaverMapCrawler(headless=True)
    fetcher = NaverRoomFetcher()
    
    query = "강남구 합주실"
    print(f"🚀 Benchmarking Full-Fetch Simulation for '{query}'...")
    
    # 1. Discovery Mode 측정
    start_time = time.time()
    results = await crawler.search_rehearsal_rooms(query)
    discovery_time = time.time() - start_time
    total_items = len(results)
    
    print(f"\n1️⃣  [Discovery Mode] Search Results")
    print(f"   - Items Found: {total_items}")
    print(f"   - Duration: {discovery_time:.2f}s")
    
    if total_items == 0:
        print("❌ No items found. Cannot proceed with fetch benchmark.")
        return

    # 2. Item Fetch Latency 측정 (샘플링)
    # 랜덤하게 10개만 골라서 상세 조회 시간 측정
    sample_size = 10
    samples = random.sample(results, min(sample_size, total_items))
    
    print(f"\n2️⃣  [Full-Fetch Simulation] Measuring latency for {len(samples)} items...")
    
    fetch_times = []
    for item in samples:
        bid = item["id"]
        # print(f"   - Fetching detail for {item['name']} ({bid})...")
        
        f_start = time.time()
        try:
            await fetcher.fetch_full_info(bid)
            f_end = time.time()
            duration = f_end - f_start
            fetch_times.append(duration)
            print(f"     ✅ Fetched {item['name']}: {duration:.2f}s")
        except Exception as e:
            print(f"     ❌ Failed {item['name']}: {e}")
            
    if not fetch_times:
        print("❌ All sample fetches failed.")
        return

    avg_fetch_time = sum(fetch_times) / len(fetch_times)
    
    # 3. 예측 (Extrapolation)
    # 전체 시간 = Discovery Time + (Total Items * Avg Fetch Time)
    # (동시성을 고려하지 않은 순차 실행 기준 - 기존 로직이 순차적이라면 이게 맞음)
    projected_total_time = discovery_time + (total_items * avg_fetch_time)
    
    print(f"\n📊 Performance Comparison")
    print(f"   - Avg Detail Fetch Time: {avg_fetch_time:.2f}s per item")
    print(f"   - [Discovery Mode] Total Time: {discovery_time:.2f}s")
    print(f"   - [Full-Fetch Mode] Projected Time: {projected_total_time:.2f}s (Extrapolated)")
    print(f"   - Speedup Factor: {projected_total_time / discovery_time:.1f}x Faster 🚀")

if __name__ == "__main__":
    asyncio.run(benchmark_simulation())
