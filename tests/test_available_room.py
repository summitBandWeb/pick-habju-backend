### 디도스 공격 관련 이슈로 보류... ###

# import pytest
# from fastapi.testclient import TestClient
# from app.main import app  # 실제 FastAPI 인스턴스 import

# client = TestClient(app)

# # 기본 mock 데이터
# def get_mock_request(room_type="dream", count=1):
#     rooms = [{"type": room_type, "name": f"{room_type}_room{i}"} for i in range(count)]
#     return {
#         "date": "2025-12-05",
#         "hour_slots": ["09:00", "10:00"],
#         "rooms": rooms
#     }

# def test_available_rooms_success():
#     req_body = get_mock_request(room_type="dream", count=1)
#     response = client.post("/api/rooms/availability/", json=req_body)
#     assert response.status_code == 200
#     resp = response.json()
#     assert resp["date"] == req_body["date"]
#     assert set(resp["hour_slots"]) == set(req_body["hour_slots"])
#     assert isinstance(resp["results"], list)
#     # more checks as needed

# def test_available_rooms_rate_limit_dream():
#     req_body = get_mock_request(room_type="dream", count=1)
#     # 250회 호출 후 251번째 요청에서 rate limit 발생해야 함
#     for i in range(250):
#         response = client.post("/api/rooms/availability/", json=req_body)
#         assert response.status_code == 200
#     # 다음 요청은 rate limit 초과
#     response = client.post("/api/rooms/availability/", json=req_body)
#     assert response.status_code == 429
#     assert "드림" in response.text or "dream" in response.text or "rate limit" in response.text

# def test_available_rooms_rate_limit_groove():
#     req_body = get_mock_request(room_type="groove", count=1)
#     for i in range(250):
#         response = client.post("/api/rooms/availability/", json=req_body)
#         assert response.status_code == 200
#     response = client.post("/api/rooms/availability/", json=req_body)
#     assert response.status_code == 429
#     assert "그루브" in response.text or "groove" in response.text

# def test_available_rooms_rate_limit_naver():
#     req_body = get_mock_request(room_type="naver", count=1)
#     for i in range(600):
#         response = client.post("/api/rooms/availability/", json=req_body)
#         assert response.status_code == 200
#     response = client.post("/api/rooms/availability/", json=req_body)
#     assert response.status_code == 429
#     assert "네이버" in response.text or "naver" in response.text

# def test_available_rooms_rate_limit_global():
#     # dream + groove + naver 요청을 합쳐 1000회 넘기면 전체 ratelimit도 동작
#     req_body_dream = get_mock_request("dream", 1)
#     req_body_groove = get_mock_request("groove", 1)
#     req_body_naver = get_mock_request("naver", 1)
#     for i in range(333):
#         assert client.post("/api/rooms/availability/", json=req_body_dream).status_code == 200
#         assert client.post("/api/rooms/availability/", json=req_body_groove).status_code == 200
#         assert client.post("/api/rooms/availability/", json=req_body_naver).status_code == 200
#     # 다음 요청에서 전체 1000회 초과 발생
#     resp = client.post("/api/rooms/availability/", json=req_body_dream)
#     assert resp.status_code == 429
#     assert "rate limit" in resp.text or "초과" in resp.text

