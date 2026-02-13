"""
서울 지역 합주실 좌표 업데이트 및 마스터 데이터 동기화 스크립트

Rationale:
    - 이 스크립트는 네이버 검색 결과를 기반으로 DB의 마스터 데이터를 동기화하는 도구입니다.
    - 기존 지점(이미 business_id가 존재하는 경우)은 좌표(lat, lng)만 업데이트하여 
      수동으로 수정되었을 수 있는 지점명 등의 데이터를 보존하고 정합성을 유지합니다.
    - 신규 지점은 전체 정보(ID, 이름, 좌표)를 삽입합니다.
    - Windows 환경의 Playwright 안정성을 위해 ProactorEventLoop를 기본값으로 사용합니다.
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
from app.core.constants import SEOUL_DISTRICTS

async def update_district(query: str, supabase, crawler):
    """검색 결과에서 좌표를 추출하여 DB 동기화 (기존은 좌표만 업데이트, 신규는 삽입)
    
    Args:
        query (str): 검색어 (예: '강남구 합주실')
        supabase: Supabase 클라이언트 객체
        crawler: NaverMapCrawler 인스턴스
        
    Returns:
        tuple: (success_count, failure_count)
        
    Rationale:
        네이버 지도 검색 결과를 기반으로 DB에 실시간 좌표를 반영합니다.
        기존 지점의 경우 이름을 업데이트에서 제외하여, 관리자가 수동으로 수정한 지점명이
        검색 결과의 비표준 이름으로 덮어씌워지는 것을 방지합니다.
    """
    try:
        # 지도 검색 호출
        results = await crawler.search_rehearsal_rooms(query)
        if not results:
            print(f"   ⚠️ '{query}' 검색 결과 없음")
            return 0, 0
            
        success_count = 0
        failure_count = 0
        for item in results:
            try:
                # y=위도(Latitude), x=경도(Longitude)
                business_id = item["id"]
                name = item["name"]
                
                # 좌표 유효성 검사 (None이거나 비어있는 경우 방어)
                if not item.get("y") or not item.get("x"):
                    print(f"      🏠 '{name}' ({business_id}) 건너뜀: 좌표 정보가 없습니다.")
                    failure_count += 1
                    continue
                
                try:
                    lat = float(item["y"])
                    lng = float(item["x"])
                    
                    # NOTE: 서울 좌표 범위 검증 (리뷰 피드백 반영: 37.4~37.7, 126.7~127.2)
                    if not (37.4 <= lat <= 37.7 and 126.7 <= lng <= 127.2):
                        print(f"      🏠 '{name}' ({business_id}) 건너뜀: 서울 범위를 벗어난 좌표 ({lat}, {lng})")
                        failure_count += 1
                        continue
                except (ValueError, TypeError) as e:
                    print(f"      ❌ '{name}' ({business_id}) 좌표 변환 실패: {e}")
                    failure_count += 1
                    continue
                
                # NOTE: 기존 데이터 존재 여부 확인 (마스터 데이터 정합성 유지)
                existing = supabase.table("branch").select("business_id").eq("business_id", business_id).execute()
                
                if existing.data:
                    # 기존 지점 -> 좌표만 업데이트하여 지점명 오염 방지
                    supabase.table("branch").update({
                        "lat": lat,
                        "lng": lng
                    }).eq("business_id", business_id).execute()
                else:
                    # 신규 지점 -> 전체 insert
                    supabase.table("branch").insert({
                        "business_id": business_id,
                        "name": name,
                        "lat": lat,
                        "lng": lng
                    }).execute()
                    
                success_count += 1
            except Exception as e:
                print(f"      ❌ '{item.get('name', 'Unknown')}' ({item.get('id')}) 처리 실패: {e}")
                failure_count += 1
                continue
        return success_count, failure_count
    except Exception as e:
        print(f"   🚨 '{query}' 처리 중 심각한 오류 발생: {e}")
        traceback.print_exc()
        return 0, 0

async def main():
    parser = argparse.ArgumentParser(description="서울 합주실 마스터 데이터 동기화")
    parser.add_argument("--start", type=int, default=0, help="시작 구 인덱스")
    parser.add_argument("--end", type=int, default=len(SEOUL_DISTRICTS), help="종료 구 인덱스")
    parser.add_argument("--delay", type=float, default=2.0, help="구별 대기 시간(초)")
    args = parser.parse_args()

    # Crawler와 Supabase 클라이언트 초기화
    crawler = NaverMapCrawler(headless=True)
    supabase = get_supabase_client()
    
    target_districts = SEOUL_DISTRICTS[args.start:args.end]
    print(f"🚀 서울 합주실 마스터 데이터 동기화 시작")
    print(f"📍 대상 범위: {args.start} ~ {args.end-1} ({len(target_districts)}개 구)")
    
    total_success = 0
    total_failure = 0
    
    for idx, query in enumerate(target_districts):
        curr_idx = args.start + idx
        print(f"\n[{curr_idx+1}/25] '{query}' 작업 중...")
        success, failure = await update_district(query, supabase, crawler)
        print(f"   ✅ 처리 완료: 성공 {success}개, 실패 {failure}개")
        total_success += success
        total_failure += failure
        
        # 마지막 구가 아니면 대기
        if idx < len(target_districts) - 1:
            await asyncio.sleep(args.delay)

    print(f"\n" + "="*50)
    print(f"🎉 모든 동기화 작업이 완료되었습니다!")
    print(f"📊 최종 통계")
    print(f"   - 성공(업데이트/삽입): {total_success}개")
    print(f"   - 실패: {total_failure}개")
    print(f"="*50)

if __name__ == "__main__":
    # Windows에서 Playwright를 사용할 때는 SelectorEventLoop를 강제하지 말고 
    # 기본값인 ProactorEventLoop를 사용해야 subprocess 생성이 가능합니다.
    asyncio.run(main())
