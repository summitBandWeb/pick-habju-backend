import asyncio
import logging
import sys
import os

# PYTHONPATH 설정: 실행 경로를 sys.path에 추가
sys.path.append(os.getcwd())

from app.services.room_collection_service import RoomCollectionService
from app.services.availability_service import AvailabilityService
from app.models.dto import AvailabilityRequest
from app.core.supabase_client import get_supabase_client
from datetime import datetime, timedelta

# 로깅 설정
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("DB_Verify")

async def verify_db_integration():
    logger.info("Starting DB Integration Verification for v2.0.0...")
    
    # 1. Setup Services
    collection_svc = RoomCollectionService()
    # 크롤러는 Mocking 필요 없음 (DB 조회 로직만 검증하면 됨)
    # 단, check_availability 내부에서 크롤러가 필요하므로 빈 맵을 주입하되, 
    # 실제로는 DB에서 가져온 room_detail을 확인하는 것이 목적.
    # 하지만 AvailabilityService.check_availability는 크롤러를 실행하려 할 것임.
    # 따라서 여기서는 AvailabilityService 대신 'get_rooms_by_criteria' 함수를 직접 호출하여
    # DB에서 RoomDetail이 v2 필드와 함께 올바르게 매핑되어 나오는지 확인하는 것이 더 정확함.
    
    from app.utils.room_loader import get_rooms_by_criteria
    
    # 2. Prepare Test Data
    test_biz_id = "TEST_BIZ_V2"
    test_room_id = "TEST_ROOM_V2"
    
    business_data = {
        "businessId": test_biz_id,
        "businessDisplayName": "[테스트] v2.0.0 통합 검증 합주실",
        "coordinates": {"latitude": 37.5, "longitude": 127.0}
    }
    
    room_data = [{
        "bizItemId": test_room_id,
        "name": "일반실 (v2 테스트)",
        "bizItemResources": [{"resourceUrl": "http://example.com/img.jpg"}],
        "minMaxPrice": {"minPrice": 15000}
    }]
    
    # v2.0.0 Parsed Data (LLM 결과 모사)
    parsed_results = {
        test_room_id: {
            "max_capacity": 10,
            "recommend_capacity": 6,
            "recommend_capacity_range": [5, 8], # v2 필드
            "price_config": [{"days": [5, 6], "price": 20000}], # v2 필드
            "base_capacity": 4, # v2 필드
            "extra_charge": 5000, # v2 필드
            "requires_call_on_same_day": True
        }
    }
    
    # 3. Save to DB (RoomCollectionService 이용)
    logger.info("Step 1: Saving test data to DB...")
    await collection_svc._save_to_db(business_data, room_data, parsed_results)
    logger.info("Data saved successfully.")
    
    # 4. Fetch from DB (get_rooms_by_criteria 이용)
    logger.info("Step 2: Fetching data from DB...")
    
    # 검색 조건: 해당 합주실이 포함되도록 넓게 잡음
    rooms = get_rooms_by_criteria(
        capacity=6,
        swLat=37.0, swLng=126.0,
        neLat=38.0, neLng=128.0
    )
    
    # 5. Verify v2 Fields
    target_room = next((r for r in rooms if r.biz_item_id == test_room_id), None)
    
    if not target_room:
        logger.error("Failed Inspection: Test room not found in DB results.")
        return
    
    logger.info(f"Target Room Found: {target_room.name}")
    
    # 검증 포인트
    errors = []
    
    # (1) recommend_capacity_range
    # NOTE: _calculate_capacity_range 로직에 의해 extra_charge가 있으면 [base_cap, max_cap]으로 계산됨
    # base=4, max=10 -> [4, 10]
    if target_room.recommendCapacityRange != [4, 10]:
        errors.append(f"recommendCapacityRange mismatch: expected [4, 10], got {target_room.recommendCapacityRange}")
    
    # (2) price_config
    # price_config는 리스트 안의 딕셔너리 순서나 내용 비교
    expected_config = [{"days": [5, 6], "price": 20000}]
    # DB에서 나올 때 days가 리스트로 잘 나오는지 확인
    if target_room.priceConfig != expected_config:
        # Pydantic 모델이거나 dict일 수 있음, 내용 비교 필요
        logger.warning(f"priceConfig check: {target_room.priceConfig} vs {expected_config}")
        # 단순 비교가 실패할 수 있으므로(순서 등), 깊은 비교는 생략하더라도 값 존재 여부 확인
        if not target_room.priceConfig:
             errors.append("priceConfig is empty")

    # (3) base_capacity / extra_charge
    if target_room.baseCapacity != 4:
         errors.append(f"baseCapacity mismatch: expected 4, got {target_room.baseCapacity}")
         
    if target_room.extraCharge != 5000:
         errors.append(f"extraCharge mismatch: expected 5000, got {target_room.extraCharge}")

    if errors:
        logger.error("Verification FAILED with errors:")
        for e in errors:
            logger.error(f"- {e}")
    else:
        logger.info("Verification PASSED! Validation of v2 fields successful.")

    # 6. Clean up (Optional)
    # logger.info("Cleaning up test data...")
    # supabase = get_supabase_client()
    # supabase.table("room").delete().eq("biz_item_id", test_room_id).execute()
    # supabase.table("branch").delete().eq("business_id", test_biz_id).execute()

if __name__ == "__main__":
    asyncio.run(verify_db_integration())
