"""
서울 지역 합주실 좌표 업데이트 스크립트 (Windows 안정화 버전)

Rationale:
    - Windows에서 Playwright 사용 시 SelectorEventLoopPolicy를 설정하면 
      subprocess 생성 시 NotImplementedError가 발생함 (기본값인 Proactor 사용 필수).
    - collect_samples.py가 성공하는 이유는 이 정책 설정을 하지 않았기 때문임.
    - 검색 결과에서 좌표를 즉시 추출하여 DB에 업데이트함으로써 속도와 성공률을 높임.
"""

import sys
import asyncio
import argparse
import traceback
from pathlib import Path

# 프로젝트 루트 추가
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.crawler.naver_map_crawler import NaverMapCrawler
from app.core.supabase_client import get_supabase_client

async def update_district(query: str, supabase, crawler):
    """검색 결과에서 좌표를 즉시 추출하여 DB 업데이트"""
    try:
        # 지도 검색 호출
        results = await crawler.search_rehearsal_rooms(query)
        if not results:
            print(f"   ⚠️ '{query}' 검색 결과 없음")
            return 0
            
        success_count = 0
        for item in results:
            try:
                # y=위도(Latitude), x=경도(Longitude)
                # item['id']는 NaverMapCrawler에서 이미 bookingBusinessId를 우선 파싱하도록 되어 있음
                supabase.table("branch").upsert({
                    "business_id": item["id"],
                    "name": item["name"],
                    "lat": float(item["y"]),
                    "lng": float(item["x"])
                }).execute()
                success_count += 1
            except Exception as e:
                # 개별 업데이트 실패는 로그만 남기고 진행
                continue
        return success_count
    except Exception as e:
        print(f"   🚨 '{query}' 처리 중 오류 발생: {e}")
        traceback.print_exc() # 상세 에러 스택 출력
        return 0

async def main():
    parser = argparse.ArgumentParser(description="서울 합주실 좌표 수집 및 업데이트")
    parser.add_argument("--start", type=int, default=0, help="시작 구 인덱스")
    parser.add_argument("--end", type=int, default=25, help="종료 구 인덱스")
    parser.add_argument("--delay", type=float, default=2.0, help="구별 대기 시간(초)")
    args = parser.parse_args()

    # Crawler와 Supabase 클라이언트 초기화
    crawler = NaverMapCrawler(headless=True)
    supabase = get_supabase_client()
    
    seoul_districts = [
        "강남구 합주실", "강동구 합주실", "강북구 합주실", "강서구 합주실", "관악구 합주실",
        "광진구 합주실", "구로구 합주실", "금천구 합주실", "노원구 합주실", "도봉구 합주실",
        "동대문구 합주실", "동작구 합주실", "마포구 합주실", "서대문구 합주실", "서초구 합주실",
        "성동구 합주실", "성북구 합주실", "송파구 합주실", "양천구 합주실", "영등포구 합주실",
        "용산구 합주실", "은평구 합주실", "종로구 합주실", "중구 합주실", "중랑구 합주실"
    ]
    
    target_districts = seoul_districts[args.start:args.end]
    print(f"🚀 서울 합주실 좌표 수집 시작 (검색 결과 직접 업데이트)")
    print(f"📍 대상: {args.start} ~ {args.end-1} ({len(target_districts)}개 구)")
    
    total = 0
    for idx, query in enumerate(target_districts):
        curr_idx = args.start + idx
        print(f"\n[{curr_idx+1}/25] '{query}' 작업 중...")
        count = await update_district(query, supabase, crawler)
        print(f"   ✅ {count}개 지점 좌표 처리 완료")
        total += count
        
        # 마지막 구가 아니면 대기
        if idx < len(target_districts) - 1:
            await asyncio.sleep(args.delay)

    print(f"\n🎉 모든 작업 완료! 총 {total}개 지점의 좌표를 업데이트했습니다.")

if __name__ == "__main__":
    # Windows에서 Playwright를 사용할 때는 SelectorEventLoop를 강제하지 말고 
    # 기본값인 ProactorEventLoop를 사용해야 subprocess 생성이 가능합니다.
    asyncio.run(main())
