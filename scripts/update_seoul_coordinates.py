"""
서울 지역 합주실 좌표 업데이트 스크립트 (안전 모드)

사용법:
    # 0번부터 4번 구까지 (강남~관악) 5개 구만 실행
    python scripts/update_seoul_coordinates.py --start 0 --end 5
    
    # 전체 실행 (기본 딜레이 7초 적용)
    python scripts/update_seoul_coordinates.py
"""

import asyncio
import logging
import sys
import argparse
from pathlib import Path

# 프로젝트 루트를 PYTHONPATH에 추가
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.services.room_collection_service import RoomCollectionService
from app.core.logging_config import setup_logging

# 로깅 설정
setup_logging()
logger = logging.getLogger("app")

async def main():
    parser = argparse.ArgumentParser(description="서울 합주실 데이터 및 좌표 업데이트")
    parser.add_argument("--start", type=int, default=0, help="시작 인덱스 (0-24)")
    parser.add_argument("--end", type=int, default=25, help="종료 인덱스 (최대 25)")
    parser.add_argument("--delay", type=int, default=7, help="구별 대기 시간(초)")
    args = parser.parse_args()

    service = RoomCollectionService()
    
    seoul_districts = [
        "강남구 합주실", "강동구 합주실", "강북구 합주실", "강서구 합주실", "관악구 합주실",
        "광진구 합주실", "구로구 합주실", "금천구 합주실", "노원구 합주실", "도봉구 합주실",
        "동대문구 합주실", "동작구 합주실", "마포구 합주실", "서대문구 합주실", "서초구 합주실",
        "성동구 합주실", "성북구 합주실", "송파구 합주실", "양천구 합주실", "영등포구 합주실",
        "용산구 합주실", "은평구 합주실", "종로구 합주실", "중구 합주실", "중랑구 합주실"
    ]
    
    # 범위 제한
    target_districts = seoul_districts[args.start:args.end]
    
    print(f"🚀 서울 합주실 업데이트 시작 ({args.start} ~ {args.end-1} 인덱스)")
    print(f"📍 대상: {', '.join([d.split()[0] for d in target_districts])}")
    print(f"⏱️ 안전 딜레이: {args.delay}초")
    
    total_success = 0
    total_failed = 0
    
    for idx, query in enumerate(target_districts):
        curr_idx = args.start + idx
        print(f"\n[{curr_idx+1}/{len(seoul_districts)}] '{query}' 수집 중...")
        
        try:
            # 실시간 로그 확인을 위해 로깅 레벨 일시 조정 가능
            result = await service.collect_by_query(query)
            success = result["success"]
            failed = result["failed"]
            
            print(f"   ✅ 결과: 성공 {success}건, 실패 {failed}건")
            total_success += success
            total_failed += failed
            
            # 마지막 요소가 아니면 대기
            if idx < len(target_districts) - 1:
                print(f"   💤 다음 구 작업을 위해 {args.delay}초 대기...")
                await asyncio.sleep(args.delay)
                
        except Exception as e:
            print(f"   🚨 '{query}' 처리 중 오류: {e}")
            logger.error(f"Error during {query}: {e}")
            # 차단 의심 시 즉시 중단 권고를 위해 break 여부 고민 (일단 계속 진행)

    print("\n" + "=" * 50)
    print("🎉 선택 범위 업데이트 완료")
    print(f"총 성공: {total_success}건 / 총 실패: {total_failed}건")
    print("=" * 50)

if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main())
