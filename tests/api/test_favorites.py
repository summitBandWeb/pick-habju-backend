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
def api_endpoint(target_biz_id):
    return f"/api/favorites/{target_biz_id}"


def test_add_favorite_success(client, api_endpoint, headers):
    """즐겨찾기 추가 성공 시 200 OK와 성공 응답을 반환해야 한다."""
    # Act
    response = client.put(api_endpoint, headers=headers)

    # Assert
    assert response.status_code == 200
    assert response.json() == {"success": True}

def test_add_favorite_idempotency(client, api_endpoint, headers):
    """이미 존재하는 즐겨찾기를 다시 추가해도 에러 없이 200 OK를 반환해야 한다 (멱등성)."""
    # Arrange: 이미 추가된 상태
    client.put(api_endpoint, headers=headers)

    # Act: 중복 추가 시도
    response = client.put(api_endpoint, headers=headers)

    # Assert
    assert response.status_code == 200
    assert response.json() == {"success": True}

def test_delete_favorite_success(client, api_endpoint, headers):
    """즐겨찾기 삭제 성공 시 200 OK를 반환해야 한다."""
    # Arrange: 데이터 준비
    client.put(api_endpoint, headers=headers)

    # Act
    response = client.delete(api_endpoint, headers=headers)

    # Assert
    assert response.status_code == 200
    assert response.json() == {"success": True}

def test_delete_favorite_idempotency(client, api_endpoint, headers):
    """존재하지 않는 즐겨찾기를 삭제해도 에러 없이 200 OK를 반환해야 한다."""
    # Act: 없는 데이터 삭제 시도
    response = client.delete(api_endpoint, headers=headers)

    # Assert
    assert response.status_code == 200
    assert response.json() == {"success": True}

@pytest.mark.parametrize("invalid_headers, expected_detail", [
    ({}, "X-Device-Id header is required and cannot be empty"),                      # 헤더 누락
    ({"X-Device-Id": ""}, "X-Device-Id header is required and cannot be empty"),     # 빈 헤더
    ({"X-Device-Id": "   "}, "X-Device-Id header is required and cannot be empty"),  # 공백 헤더
    ({"X-Device-Id": "not-a-uuid"}, "Invalid X-Device-Id format"), # 잘못된 형식
])
def test_favorite_error_cases(client, api_endpoint, invalid_headers, expected_detail):
    """잘못된 헤더 요청에 대해 적절한 400 에러를 반환해야 한다."""
    # Act
    response = client.put(api_endpoint, headers=invalid_headers)

    # Assert
    assert response.status_code == 400
    assert response.json()["detail"] == expected_detail
