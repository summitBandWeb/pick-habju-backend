from fastapi.testclient import TestClient
from app.main import app
from app.api.dependencies import get_favorite_repository
from app.repositories.memory import MockFavoriteRepository

# Mock Repository를 테스트 전용으로 초기화하여 사용
def override_get_favorite_repository():
    return MockFavoriteRepository()

app.dependency_overrides[get_favorite_repository] = override_get_favorite_repository

client = TestClient(app)

def test_add_favorite_success():
    # 1. 신규 추가 (201 Created)
    response = client.put(
        "/api/favorites/biz-123",
        headers={"X-Device-Id": "device-A"}
    )
    assert response.status_code == 201
    assert response.json() == {"status": "created", "biz_item_id": "biz-123"}

def test_add_favorite_idempotency():
    # 1. 초기 상태 추가
    client.put(
        "/api/favorites/biz-999",
        headers={"X-Device-Id": "device-B"}
    )
    
    # 2. 중복 추가 시도 (200 OK)
    response = client.put(
        "/api/favorites/biz-999",
        headers={"X-Device-Id": "device-B"}
    )
    assert response.status_code == 200
    # Response body는 없거나 빈 상태일 수 있음 (구현에 따라 다름, 현재는 Response(200)만 리턴)

def test_delete_favorite_success():
    # 1. 데이터 준비
    client.put(
        "/api/favorites/biz-del-1",
        headers={"X-Device-Id": "device-C"}
    )
    
    # 2. 삭제 요청 (200 OK)
    response = client.delete(
        "/api/favorites/biz-del-1",
        headers={"X-Device-Id": "device-C"}
    )
    assert response.status_code == 200
    assert response.json() == {"status": "deleted"}

def test_delete_favorite_idempotency():
    # 1. 없는 데이터 삭제 시도 (200 OK) - 에러가 나면 안 됨
    response = client.delete(
        "/api/favorites/biz-none",
        headers={"X-Device-Id": "device-D"}
    )
    assert response.status_code == 200
    assert response.json() == {"status": "deleted"}

def test_missing_header_error():
    # 1. 헤더 누락 시 (400 Bad Request)
    response = client.put("/api/favorites/biz-err")
    assert response.status_code == 400
    assert response.json()["detail"] == "X-Device-Id header missing"
