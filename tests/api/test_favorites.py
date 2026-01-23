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
    # 1. 신규 추가 (200 OK)
    response = client.put(
        "/api/favorites/biz-123",
        headers={"X-Device-Id": "550e8400-e29b-41d4-a716-446655440000"}  # Valid UUID
    )
    assert response.status_code == 200
    assert response.json() == {"success": True}

def test_add_favorite_idempotency():
    # 1. 초기 상태 추가
    client.put(
        "/api/favorites/biz-999",
        headers={"X-Device-Id": "550e8400-e29b-41d4-a716-446655440000"}
    )
    
    # 2. 중복 추가 시도 (200 OK)
    response = client.put(
        "/api/favorites/biz-999",
        headers={"X-Device-Id": "550e8400-e29b-41d4-a716-446655440000"}
    )
    assert response.status_code == 200
    assert response.json() == {"success": True}

def test_delete_favorite_success():
    # 1. 데이터 준비
    client.put(
        "/api/favorites/biz-del-1",
        headers={"X-Device-Id": "550e8400-e29b-41d4-a716-446655440000"}
    )
    
    # 2. 삭제 요청 (200 OK)
    response = client.delete(
        "/api/favorites/biz-del-1",
        headers={"X-Device-Id": "550e8400-e29b-41d4-a716-446655440000"}
    )
    assert response.status_code == 200
    assert response.json() == {"success": True}

def test_delete_favorite_idempotency():
    # 1. 없는 데이터 삭제 시도 (200 OK) - 에러가 나면 안 됨
    response = client.delete(
        "/api/favorites/biz-none",
        headers={"X-Device-Id": "550e8400-e29b-41d4-a716-446655440000"}
    )
    assert response.status_code == 200
    assert response.json() == {"success": True}

def test_missing_header_error():
    # 1. 헤더 누락 시 (400 Bad Request)
    response = client.put("/api/favorites/biz-err")
    assert response.status_code == 400
    assert response.json()["detail"] == "X-Device-Id header missing"

def test_invalid_uuid_error():
    # 1. 잘못된 UUID 형식 (400 Bad Request)
    response = client.put(
        "/api/favorites/biz-err-uuid",
        headers={"X-Device-Id": "invalid-uuid-string"}
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "Invalid X-Device-Id format"
