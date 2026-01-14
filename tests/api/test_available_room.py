from fastapi.testclient import TestClient
from typing import List, Dict
from unittest.mock import MagicMock
from app.main import app
from app.crawler.base import BaseCrawler, RoomResult
from app.models.dto import RoomAvailability, RoomKey
from app.api.dependencies import get_crawlers_map

client = TestClient(app)

# --- Mock Crawler Definition ---
class MockCrawler(BaseCrawler):
    def __init__(self, name: str):
        self.name = name

    async def check_availability(self, date: str, hour_slots: List[str], rooms: List[RoomKey]) -> List[RoomResult]:
        # Return dummy data for any room requested
        results = []
        for room in rooms:
            slots = {slot: True for slot in hour_slots}
            results.append(RoomAvailability(
                name=room.name,
                branch=room.branch,
                business_id=room.business_id,
                biz_item_id=room.biz_item_id,
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

def test_post_availability_api():
    # POST 요청 테스트 - Mock 크롤러를 통해 동작 검증
    url = "/api/rooms/availability"
    target_date = (datetime.now() + timedelta(days=2)).strftime("%Y-%m-%d")
    payload = {
        "date": target_date,
        "hour_slots": ["18:00", "19:00", "20:00"],
        "rooms": [
            {
                "name": "블랙룸",
                "branch": "비쥬합주실 1호점",
                "business_id": "522011",
                "biz_item_id": "3968885"
            },
            {
                "name": "B룸",
                "branch": "비쥬합주실 2호점",
                "business_id": "706924",
                "biz_item_id": "4450073"
            },
        ]
    }

    # API 호출 (MockCrawler가 주입되어 실행됨)
    response = client.post(
        url=url,
        json=payload,
    )

    assert response.status_code == 200
    data = response.json()
    assert data.get("date") == target_date
    assert data.get("hour_slots") == ["18:00", "19:00", "20:00"]
    assert "available_biz_item_ids" in data
    # MockCrawler는 항상 True를 반환하므로 결과가 있어야 함
    assert len(data["results"]) == 2


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


def test_post_availability_api_with_crawler_error():
    """크롤러에서 예외가 발생해도 API가 정상 응답하는지 검증 (리뷰 피드백 3.1)"""
    
    # 1. 예외를 발생시키는 Mock Crawler 정의
    class ErrorCrawler(BaseCrawler):
        async def check_availability(self, date: str, hour_slots: List[str], rooms: List[RoomKey]) -> List[RoomResult]:
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
    
    try:
        url = "/api/rooms/availability"
        target_date = (datetime.now() + timedelta(days=2)).strftime("%Y-%m-%d")
        payload = {
            "date": target_date,
            "hour_slots": ["18:00"],
            "rooms": [
                # 1. Naver Room (ErrorCrawler) - business_id != "dream_sadang" and != "sadang"
                {
                    "name": "Naver Room",
                    "branch": "Branch 1",
                    "business_id": "123456", 
                    "biz_item_id": "111"
                },
                # 2. Dream Room (NormalCrawler) - business_id == "dream_sadang"
                {
                    "name": "Dream Room",
                    "branch": "Dream Branch",
                    "business_id": "dream_sadang",
                    "biz_item_id": "222"
                }
            ]
        }
        # Validation Bypass
        from unittest.mock import patch
        with patch("app.validate.request_validator.validate_room_key_list") as mock_validator:
            response = client.post(url, json=payload)
        
        assert response.status_code == 200
        data = response.json()
        
        # Naver(Error) 결과는 제외되고, Dream(Normal) 결과만 있어야 함
        # NormalCrawler가 반환한 결과 1개 (room 1개)
        
        assert len(data["results"]) == 1
        assert data["results"][0]["business_id"] == "dream_sadang"
        assert data["results"][0]["available"] is True

    finally:
        # 복원
        if original_override:
            app.dependency_overrides[get_crawlers_map] = original_override
        else:
            del app.dependency_overrides[get_crawlers_map]
