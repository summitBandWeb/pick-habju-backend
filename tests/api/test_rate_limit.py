from fastapi.testclient import TestClient
from datetime import datetime, timedelta
import pytest
from app.main import app

client = TestClient(app)

@pytest.fixture(autouse=True)
def reset_limiter():
    """각 테스트 전에 limiter storage를 리셋"""
    from app.core.limiter import limiter
    limiter.reset()
    yield

def test_rate_limit_exceeded():
    """
    Rate Limit (1분당 5회) 초과 시 429 에러 및 커스텀 에러 포맷 검증
    """
    url = "/api/rooms/availability"
    
    # query parameter 준비 (capacity=100으로 설정하여 크롤링 로직 skip)
    params = {
        "date": (datetime.now() + timedelta(days=2)).strftime("%Y-%m-%d"),
        "capacity": 100,  
        "start_hour": "18:00",
        "end_hour": "21:00"
    }

    # 처음 5번 요청은 성공(200) 또는 400/404 (로직상) 이어야 함.
    # 하지만 429는 아니어야 함.
    for i in range(5):
        # reset_limiter fixture 덕분에 매 테스트마다 카운트가 초기화됨
        response = client.get(url, params=params)
        
        # 정상적인 경우 200 또는 400(데이터 없음) 등이 나와야 함
        assert response.status_code != 429, f"Request {i+1} failed with 429"

    # 6번째 요청: Rate Limit 걸려야 함
    response = client.get(url, params=params)
    
    assert response.status_code == 429
    data = response.json()
    
    # 커스텀 에러 포맷 검증
    assert data["status"] == 429
    assert data["errorCode"] == "RateLimit-001"
    assert "요청 횟수가 초과되었습니다" in data["message"]
    assert "timestamp" in data
