# te/test_naver_checker.py
import pytest

from datetime import datetime, timedelta
from app.crawler.naver_checker import NaverCrawler
from app.models.dto import RoomDetail
from app.utils.room_loader import get_rooms_by_criteria

@pytest.mark.asyncio
async def test_get_naver_availability():
    # 실제 테스트용 파라미터를 여기에 입력하세요
    date = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
    hour_slots = ["15:00", "16:00", "17:00"]
    naver_rooms = []
    for item in get_rooms_by_criteria(capacity=1):
        if item.branch != "그루브 사당점" and item.branch != "드림합주실 사당점":
            room = RoomDetail(
                name=item.name,
                branch=item.branch,
                business_id=item.business_id,
                biz_item_id=item.biz_item_id,
                imageUrls=item.imageUrls,
                maxCapacity=item.maxCapacity,
                recommendCapacity=item.recommendCapacity,
                pricePerHour=item.pricePerHour,
                canReserveOneHour=item.canReserveOneHour,
                requiresCallOnSameDay=item.requiresCallOnSameDay
            )
            naver_rooms.append(room)

    crawler = NaverCrawler()
    result = await crawler.check_availability(date, hour_slots, naver_rooms)
    
    # 성공/실패 분리
    success_results = [r for r in result if not isinstance(r, Exception)]
    error_results = [r for r in result if isinstance(r, Exception)]
    
    if error_results:
        print(f"\n⚠️ {len(error_results)}개 룸 조회 실패:")
        for err in error_results:
            print(f"  - {err}")
    
    print(f"\n✅ {len(success_results)}개 룸 조회 성공")

    # 검증: 최소 하나 이상 성공해야 함 (크롤러 정상 작동 확인)
    assert isinstance(result, list)
    assert len(success_results) > 0, "모든 룸 조회가 실패했습니다. 네트워크 또는 API 문제일 수 있습니다."
    assert all(hasattr(r, "available_slots") for r in success_results)

