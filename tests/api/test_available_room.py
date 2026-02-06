from fastapi.testclient import TestClient
from typing import List, Dict
from unittest.mock import MagicMock, patch
import pytest
from app.main import app
from app.crawler.base import BaseCrawler, RoomResult
from app.models.dto import RoomAvailability, RoomDetail
from app.api.dependencies import get_crawlers_map

client = TestClient(app)

# --- Mock Crawler Definition ---
class MockCrawler(BaseCrawler):
    def __init__(self, name: str):
        self.name = name

    async def check_availability(self, date: str, hour_slots: List[str], rooms: List[RoomDetail]) -> List[RoomResult]:
        # Return dummy data for any room requested
        results = []
        for room in rooms:
            slots = {slot: True for slot in hour_slots}
            results.append(RoomAvailability(
                room_detail=room,
                available=True,
                available_slots=slots
            ))
        return results

# Override dependency
def override_get_crawlers_map() -> Dict[str, BaseCrawler]:
    return {
        "naver": MockCrawler("naver"),
        "dream": MockCrawler("dream"),
        "groove": MockCrawler("groove")
    }

app.dependency_overrides[get_crawlers_map] = override_get_crawlers_map


def test_ping():
    # GET 요청 테스트
    response = client.get("/ping")
    assert response.status_code == 200
    assert response.json() == {"ok": True}


from datetime import datetime, timedelta

def test_get_availability_api():
    # GET 요청 테스트 - Mock 크롤러를 통해 동작 검증
    url = "/api/rooms/availability"
    target_date = (datetime.now() + timedelta(days=2)).strftime("%Y-%m-%d")
    
    # RoomDetail 필드를 모두 포함한 Payload
    rooms_payload = [
        {
            "name": "블랙룸",
            "branch": "비쥬합주실 1호점",
            "business_id": "522011",
            "biz_item_id": "3968885",
            "imageUrls": ["img1.jpg"],
            "maxCapacity": 10,
            "recommendCapacity": 5,
            "pricePerHour": 15000,
            "canReserveOneHour": True,
            "requiresCallOnSameDay": False
        },
        {
            "name": "B룸",
            "branch": "비쥬합주실 2호점",
            "business_id": "706924",
            "biz_item_id": "4450073",
            "imageUrls": ["img2.jpg"],
            "maxCapacity": 8,
            "recommendCapacity": 4,
            "pricePerHour": 12000,
            "canReserveOneHour": True,
            "requiresCallOnSameDay": False
        },
    ]
    
    # get_rooms_by_criteria가 RoomDetail 객체 리스트를 반환하도록 Mocking
    mock_room_details = [RoomDetail(**r) for r in rooms_payload]
    
    with patch("app.services.availability_service.get_rooms_by_criteria", return_value=mock_room_details):
        # API 호출 (Mandatory coordinate parameters added)
        response = client.get(
            f"{url}?date={target_date}&capacity=3&start_hour=18:00&end_hour=21:00&swLat=37.0&swLng=127.0&neLat=38.0&neLng=128.0"
        )


        assert response.status_code == 200
        data = response.json()
        assert data.get("isSuccess") is True
        result = data.get("result")
        assert result.get("date") == target_date
        assert result.get("hour_slots") == ["18:00", "19:00", "20:00", "21:00"]
        assert "available_biz_item_ids" in result
        # MockCrawler는 항상 True를 반환하므로 결과가 있어야 함
        assert len(result["results"]) == 2
        # branch_summary가 있어야 함 (지도 기능 확장)
        assert "branch_summary" in result



def test_preflight_request():
    # CORS Preflight 요청 시뮬레이션
    habju = "https://www.pickhabju.com"
    url = "/api/rooms/availability"

    response = client.options(
        url=url,
        headers={
            "Origin": habju,  # 허용된 Origin 중 하나
            "Access-Control-Request-Method": "POST",  # 요청할 실제 메서드
            "Access-Control-Request-Headers": "Content-Type, Authorization",  # 요청할 사용자 정의 헤더
        }
    )

    # 1. 상태 코드 확인: Preflight 요청은 보통 200 OK를 반환합니다.
    assert response.status_code == 200

    # 2. 필수 응답 헤더 확인
    # 응답에 요청된 Origin이 포함된 Access-Control-Allow-Origin 헤더가 있는지 확인
    assert "access-control-allow-origin" in response.headers
    assert response.headers["access-control-allow-origin"] == habju

    # 요청된 메서드가 허용되는지 확인
    assert "access-control-allow-methods" in response.headers
    assert "POST" in response.headers["access-control-allow-methods"]

    # 요청된 헤더가 허용되는지 확인
    assert "access-control-allow-headers" in response.headers
    assert "content-type" in response.headers["access-control-allow-headers"].lower()
    assert "authorization" in response.headers["access-control-allow-headers"].lower()


def test_get_availability_api_with_crawler_error():
    """크롤러에서 예외가 발생해도 API가 정상 응답하는지 검증 (리뷰 피드백 3.1)"""
    
    # 1. 예외를 발생시키는 Mock Crawler 정의
    class ErrorCrawler(BaseCrawler):
        async def check_availability(self, date: str, hour_slots: List[str], rooms: List[RoomDetail]) -> List[RoomResult]:
            # 예외를 반환하는 크롤러
            from app.exception.crawler.naver_exception import NaverAvailabilityError
            return [NaverAvailabilityError("Test error")]

    # 2. 정상 동작하는 Mock Crawler (기존 MockCrawler 재사용)
    normal_crawler = MockCrawler("normal")

    # 3. Dependency Override (실제 키 "naver", "dream" 사용)
    def override_with_error():
        # "naver" -> ErrorCrawler
        # "dream" -> NormalCrawler
        return {
            "naver": ErrorCrawler(),
            "dream": normal_crawler
        }
    
    original_override = app.dependency_overrides.get(get_crawlers_map)
    app.dependency_overrides[get_crawlers_map] = override_with_error
    
    rooms_payload = [
        # 1. Naver Room (ErrorCrawler) - business_id != "dream_sadang" and != "sadang"
        {
            "name": "Naver Room",
            "branch": "Branch 1",
            "business_id": "123456", 
            "biz_item_id": "111",
            "imageUrls": ["img_n.jpg"],
            "maxCapacity": 5,
            "recommendCapacity": 5,
            "pricePerHour": 10000,
            "canReserveOneHour": True,
            "requiresCallOnSameDay": False
        },
        # 2. Dream Room (NormalCrawler) - business_id == "dream_sadang"
        {
            "name": "Dream Room",
            "branch": "Dream Branch",
            "business_id": "dream_sadang",
            "biz_item_id": "222",
            "imageUrls": ["img_d.jpg"],
            "maxCapacity": 5,
            "recommendCapacity": 5,
            "pricePerHour": 10000,
            "canReserveOneHour": True,
            "requiresCallOnSameDay": False
        }
    ]

    try:
        url = "/api/rooms/availability"
        target_date = (datetime.now() + timedelta(days=2)).strftime("%Y-%m-%d")
        
        # RoomDetail 객체 리스트 Mocking
        mock_room_details = [RoomDetail(**r) for r in rooms_payload]

        # Validation Bypass
        with patch("app.validate.request_validator.validate_room_detail_list") as mock_validator, \
             patch("app.services.availability_service.get_rooms_by_criteria", return_value=mock_room_details):
             
            response = client.get(
                f"{url}?date={target_date}&capacity=3&start_hour=18:00&end_hour=19:00&swLat=37.0&swLng=127.0&neLat=38.0&neLng=128.0"
            )

        
        assert response.status_code == 200
        data = response.json()
        result = data.get("result")
        
        # Naver(Error) 결과는 제외되고, Dream(Normal) 결과만 있어야 함
        # NormalCrawler가 반환한 결과 1개 (room 1개)
        
        assert len(result["results"]) == 1
        assert result["results"][0]["room_detail"]["business_id"] == "dream_sadang"  # business_id field (actual DB column)
        assert result["results"][0]["available"] is True

    finally:
        # 복원
        if original_override:
            app.dependency_overrides[get_crawlers_map] = original_override
        else:
            del app.dependency_overrides[get_crawlers_map]
            
import os

@pytest.mark.skip(
    reason="[#111] DB에 데이터가 없는 상태에서 필수 좌표 파라미터 적용 시 Room-003 에러 발생하므로 일시 중단"
)
def test_get_availability_with_real_db():

    """
    실제 Supabase와 연동하여 데이터 로드 검증 (Integration Test)
    - Mock을 사용하지 않고 실제 endpoint를 호출
    - DB 연결 및 쿼리가 정상적으로 수행되는지 확인
    """
    # 1. 현재 설정된 Mock Override 제거 (실제 서비스/크롤러 사용)
    # 기존 override 백업
    original_overrides = app.dependency_overrides.copy()
    app.dependency_overrides.clear()
    
    try:
        url = "/api/rooms/availability"
        # 충분히 미래 날짜로 설정
        target_date = (datetime.now() + timedelta(days=3)).strftime("%Y-%m-%d")
        
        # 실제 DB에 데이터가 존재할 것으로 예상되는 조건 (대한민국 전체 범위로 확대)
        response = client.get(
            f"{url}?date={target_date}&capacity=1&start_hour=18:00&end_hour=19:00&swLat=30.0&swLng=120.0&neLat=45.0&neLng=140.0"
        )


        
        # 2. 응답 검증
        assert response.status_code == 200
        data = response.json()
        result = data.get("result")
        
        # 기본 응답 구조 확인
        assert result.get("date") == target_date
        assert "results" in result
        assert isinstance(result["results"], list)
        
        # 실제 데이터가 조회되었는지 확인
        if len(result["results"]) > 0:
            first_room = result["results"][0]
            assert "room_detail" in first_room
            assert "available" in first_room
            
            # 필드 확인
            assert "business_id" in first_room["room_detail"]
            assert "name" in first_room["room_detail"]
            
            print(f"✅ Real DB Test Success: Found {len(result['results'])} rooms")
        else:
            print("⚠️ Real DB Test Warning: No rooms found (check DB data)")

    finally:
        # Override 복구
        app.dependency_overrides = original_overrides