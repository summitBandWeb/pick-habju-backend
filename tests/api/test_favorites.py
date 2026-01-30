import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.api.dependencies import get_favorite_repository
from app.repositories.memory import MockFavoriteRepository

@pytest.fixture
def mock_repo():
    """각 테스트마다 독립적인 Mock Repository 인스턴스 생성"""
    return MockFavoriteRepository()

@pytest.fixture
def client(mock_repo):
    """Dependency override가 적용된 TestClient 제공 및 자동 정리"""
    app.dependency_overrides[get_favorite_repository] = lambda: mock_repo
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()

@pytest.fixture
def valid_uuid():
    return "550e8400-e29b-41d4-a716-446655440000"

@pytest.fixture
def headers(valid_uuid):
    """공통으로 사용되는 유효한 헤더 정보"""
    return {"X-Device-Id": valid_uuid}

@pytest.fixture
def target_biz_id():
    return "biz-12345"

@pytest.fixture
def target_business_id():
    return "dream_sadang"

@pytest.fixture
def api_endpoint(target_biz_id):
    return f"/api/favorites/{target_biz_id}"


def test_add_favorite_success(client, api_endpoint, headers, target_business_id):
    """즐겨찾기 추가 성공 시 200 OK와 성공 응답을 반환해야 한다."""
    # Act
    response = client.put(api_endpoint, headers=headers, params={"business_id": target_business_id})

    # Assert
    assert response.status_code == 200
    data = response.json()
    assert data["isSuccess"] is True
    assert data["result"] == {"added": True}

def test_add_favorite_idempotency(client, api_endpoint, headers, target_business_id):
    """이미 존재하는 즐겨찾기를 다시 추가해도 에러 없이 200 OK를 반환해야 한다 (멱등성)."""
    # Arrange: 이미 추가된 상태
    client.put(api_endpoint, headers=headers, params={"business_id": target_business_id})

    # Act: 중복 추가 시도
    response = client.put(api_endpoint, headers=headers, params={"business_id": target_business_id})

    # Assert
    assert response.status_code == 200
    data = response.json()
    assert data["isSuccess"] is True
    assert data["result"] == {"added": True}

def test_delete_favorite_success(client, api_endpoint, headers, target_business_id):
    """즐겨찾기 삭제 성공 시 200 OK를 반환해야 한다."""
    # Arrange: 데이터 준비
    client.put(api_endpoint, headers=headers, params={"business_id": target_business_id})

    # Act
    response = client.delete(api_endpoint, headers=headers, params={"business_id": target_business_id})

    # Assert
    assert response.status_code == 200
    data = response.json()
    assert data["isSuccess"] is True
    assert data["result"] == {"deleted": True}
    
    # Verify actual deletion in Mock Repository

def test_delete_actually_removes_data(client, headers, api_endpoint, target_biz_id, target_business_id):
    """삭제 후 데이터가 실제로 조회되지 않는지 확인"""
    # 1. 추가
    client.put(api_endpoint, headers=headers, params={"business_id": target_business_id})
    
    # 2. 삭제
    client.delete(api_endpoint, headers=headers, params={"business_id": target_business_id})
    
    # 3. 조회 (GET) 하여 리스트에 없는지 확인
    response = client.get("/api/favorites", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert target_biz_id not in data["result"]["biz_item_ids"]

def test_delete_favorite_idempotency(client, api_endpoint, headers, target_business_id):
    """존재하지 않는 즐겨찾기를 삭제해도 에러 없이 200 OK를 반환해야 한다."""
    # Act: 없는 데이터 삭제 시도
    response = client.delete(api_endpoint, headers=headers, params={"business_id": target_business_id})

    # Assert
    assert response.status_code == 200
    data = response.json()
    assert data["isSuccess"] is True
    assert data["result"] == {"deleted": True}

@pytest.mark.parametrize("invalid_headers, expected_detail", [
    ({}, "X-Device-Id header is required and cannot be empty"),                      # 헤더 누락
    ({"X-Device-Id": ""}, "X-Device-Id header is required and cannot be empty"),     # 빈 헤더
    ({"X-Device-Id": "   "}, "X-Device-Id header is required and cannot be empty"),  # 공백 헤더
    ({"X-Device-Id": "not-a-uuid"}, "Invalid X-Device-Id format"), # 잘못된 형식
])
def test_favorite_error_cases(client, api_endpoint, invalid_headers, expected_detail, target_business_id):
    """잘못된 헤더 요청에 대해 적절한 400 에러를 반환해야 한다."""
    # Act
    # business_id를 제공하여 422 Validation Error가 아닌 Header Check 로직까지 도달하도록 함
    response = client.put(api_endpoint, headers=invalid_headers, params={"business_id": target_business_id})

    # Assert
    assert response.status_code == 400
    assert response.json()["message"] == expected_detail


# --------------------------------------------------------------------------
# GET Method Tests
# --------------------------------------------------------------------------

def test_get_favorites_empty(client, headers):
    """즐겨찾기 목록이 없을 때 빈 리스트를 반환해야 한다."""
    response = client.get("/api/favorites", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert data["isSuccess"] is True
    assert data["result"] == {"biz_item_ids": []}

def test_get_favorites_success(client, headers, target_business_id):
    """추가된 즐겨찾기 목록을 정확히 반환해야 한다."""
    # Arrange: 2개 추가
    items = ["biz-101", "biz-102"]
    for item in items:
        client.put(f"/api/favorites/{item}", headers=headers, params={"business_id": target_business_id})

    # Act
    response = client.get("/api/favorites", headers=headers)

    # Assert
    assert response.status_code == 200
    data = response.json()
    assert data["isSuccess"] is True
    assert "biz_item_ids" in data["result"]
    assert sorted(data["result"]["biz_item_ids"]) == sorted(items)

def test_get_favorites_isolation(client, headers, target_business_id):
    """다른 사용자의 즐겨찾기는 조회되지 않아야 한다."""
    # Arrange: Target User (headers)에 data adding
    my_item = "my-biz-001"
    client.put(f"/api/favorites/{my_item}", headers=headers, params={"business_id": target_business_id})

    # Arrange: Other User adding data
    # 다른 사용자용 유효한 UUID
    other_uuid = "99999999-9999-9999-9999-999999999999"
    other_headers = {"X-Device-Id": other_uuid}
    other_item = "other-biz-999"
    client.put(f"/api/favorites/{other_item}", headers=other_headers, params={"business_id": target_business_id})

    # Act: Target User gets list
    response = client.get("/api/favorites", headers=headers)

    # Assert
    data = response.json()
    assert data["isSuccess"] is True
    result = data["result"]
    assert my_item in result["biz_item_ids"]
    assert other_item not in result["biz_item_ids"]
    assert len(result["biz_item_ids"]) == 1

def test_get_favorites_error_cases(client):
    """GET 요청 시에도 잘못된 헤더에 대해 400 에러를 반환해야 한다."""
    # 헤더 누락
    response = client.get("/api/favorites", headers={})
    assert response.status_code == 400
    assert response.json()["message"] == "X-Device-Id header is required and cannot be empty"
