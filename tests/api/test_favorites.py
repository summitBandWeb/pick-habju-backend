import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.api.dependencies import get_favorite_repository
from app.repositories.memory import MockFavoriteRepository
from app.api.favorites import MAX_FAVORITES_PER_DEVICE
from app.exception.api.favorite_exception import FavoriteRepositoryUnavailableError

@pytest.fixture
def mock_repo():
    """媛??뚯뒪?몃쭏???낅┰?곸씤 Mock Repository ?몄뒪?댁뒪 ?앹꽦"""
    return MockFavoriteRepository()

@pytest.fixture
def client(mock_repo):
    """Dependency override媛 ?곸슜??TestClient ?쒓났 諛??먮룞 ?뺣━"""
    app.dependency_overrides[get_favorite_repository] = lambda: mock_repo
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()

@pytest.fixture
def valid_uuid():
    return "550e8400-e29b-41d4-a716-446655440000"

@pytest.fixture
def headers(valid_uuid):
    """怨듯넻?쇰줈 ?ъ슜?섎뒗 ?좏슚???ㅻ뜑 ?뺣낫"""
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
    """利먭꺼李얘린 異붽? ?깃났 ??200 OK? ?깃났 ?묐떟??諛섑솚?댁빞 ?쒕떎."""
    # Act
    response = client.put(api_endpoint, headers=headers, params={"business_id": target_business_id})

    # Assert
    assert response.status_code == 200
    data = response.json()
    assert data["isSuccess"] is True
    assert data["result"] == {"added": True}

def test_add_favorite_idempotency(client, api_endpoint, headers, target_business_id):
    """?대? 議댁옱?섎뒗 利먭꺼李얘린瑜??ㅼ떆 異붽??대룄 ?먮윭 ?놁씠 200 OK瑜?諛섑솚?댁빞 ?쒕떎 (硫깅벑??."""
    # Arrange: ?대? 異붽????곹깭
    client.put(api_endpoint, headers=headers, params={"business_id": target_business_id})

    # Act: 以묐났 異붽? ?쒕룄
    response = client.put(api_endpoint, headers=headers, params={"business_id": target_business_id})

    # Assert
    assert response.status_code == 200
    data = response.json()
    assert data["isSuccess"] is True
    assert data["result"] == {"added": True}

def test_add_favorite_limit_exceeded(client, headers, target_business_id, mock_repo):
    """理쒕? 利먭꺼李얘린 媛쒖닔瑜?珥덇낵?섎㈃ 400 ?먮윭瑜?諛섑솚?댁빞 ?쒕떎."""
    
    # Arrange: ?쒕룄瑜?媛??梨꾩?
    for i in range(MAX_FAVORITES_PER_DEVICE):
        mock_repo.add(device_id=headers["X-Device-Id"], business_id=target_business_id, biz_item_id=f"item-{i}")
        
    # Act: 21踰덉㎏ 異붽?
    response = client.put("/api/favorites/new-item-over-limit", headers=headers, params={"business_id": target_business_id})
    
    # Assert
    assert response.status_code == 400
    data = response.json()
    assert data["isSuccess"] is False
    assert data["code"] == "COMMON-002"

def test_delete_favorite_success(client, api_endpoint, headers, target_business_id):
    """利먭꺼李얘린 ??젣 ?깃났 ??200 OK瑜?諛섑솚?댁빞 ?쒕떎."""
    # Arrange: ?곗씠??以鍮?
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
    """??젣 ???곗씠?곌? ?ㅼ젣濡?議고쉶?섏? ?딅뒗吏 ?뺤씤"""
    # 1. 異붽?
    client.put(api_endpoint, headers=headers, params={"business_id": target_business_id})
    
    # 2. ??젣
    client.delete(api_endpoint, headers=headers, params={"business_id": target_business_id})
    
    # 3. 議고쉶 (GET) ?섏뿬 由ъ뒪?몄뿉 ?녿뒗吏 ?뺤씤
    response = client.get("/api/favorites", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert target_biz_id not in data["result"]["biz_item_ids"]

def test_delete_favorite_idempotency(client, api_endpoint, headers, target_business_id):
    """議댁옱?섏? ?딅뒗 利먭꺼李얘린瑜???젣?대룄 ?먮윭 ?놁씠 200 OK瑜?諛섑솚?댁빞 ?쒕떎."""
    # Act: ?녿뒗 ?곗씠????젣 ?쒕룄
    response = client.delete(api_endpoint, headers=headers, params={"business_id": target_business_id})

    # Assert
    assert response.status_code == 200
    data = response.json()
    assert data["isSuccess"] is True
    assert data["result"] == {"deleted": True}

@pytest.mark.parametrize("invalid_headers, expected_status, expected_detail", [
    ({}, 422, None),                                                                  # ?ㅻ뜑 ?꾨씫 ??FastAPI 422
    ({"X-Device-Id": ""}, 400, "X-Device-Id header is required and cannot be empty"),  # 鍮??ㅻ뜑
    ({"X-Device-Id": "   "}, 400, "X-Device-Id header is required and cannot be empty"),  # 怨듬갚 ?ㅻ뜑
    ({"X-Device-Id": "not-a-uuid"}, 400, "Invalid X-Device-Id format"),                # ?섎せ???뺤떇
])
def test_favorite_error_cases(client, api_endpoint, invalid_headers, expected_status, expected_detail, target_business_id):
    """?섎せ???ㅻ뜑 ?붿껌??????곸젅???먮윭瑜?諛섑솚?댁빞 ?쒕떎."""
    # Act
    response = client.put(api_endpoint, headers=invalid_headers, params={"business_id": target_business_id})

    # Assert
    assert response.status_code == expected_status
    if expected_detail:
        assert response.json()["message"] == expected_detail


# --------------------------------------------------------------------------
# GET Method Tests
# --------------------------------------------------------------------------

def test_get_favorites_empty(client, headers):
    """利먭꺼李얘린 紐⑸줉???놁쓣 ??鍮?由ъ뒪?몃? 諛섑솚?댁빞 ?쒕떎."""
    response = client.get("/api/favorites", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert data["isSuccess"] is True
    assert data["result"] == {"biz_item_ids": []}

def test_get_favorites_success(client, headers, target_business_id):
    """異붽???利먭꺼李얘린 紐⑸줉???뺥솗??諛섑솚?댁빞 ?쒕떎."""
    # Arrange: 2媛?異붽?
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
    """?ㅻⅨ ?ъ슜?먯쓽 利먭꺼李얘린??議고쉶?섏? ?딆븘???쒕떎."""
    # Arrange: Target User (headers)??data adding
    my_item = "my-biz-001"
    client.put(f"/api/favorites/{my_item}", headers=headers, params={"business_id": target_business_id})

    # Arrange: Other User adding data
    # ?ㅻⅨ ?ъ슜?먯슜 ?좏슚??UUID
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
    """GET ?붿껌 ?쒖뿉???섎せ???ㅻ뜑??????먮윭瑜?諛섑솚?댁빞 ?쒕떎."""
    # ?ㅻ뜑 ?꾨씫 ??Header(...)?대?濡?FastAPI媛 422 諛섑솚
    response = client.get("/api/favorites", headers={})
    assert response.status_code == 422


def test_add_favorite_returns_503_when_repository_exists_check_fails(target_business_id):
    class FailingExistsRepository(MockFavoriteRepository):
        def exists(self, device_id: str, business_id: str, biz_item_id: str) -> bool:  # noqa: ARG002
            raise FavoriteRepositoryUnavailableError("以묐났 ?뺤씤 ?ㅽ뙣")

    app.dependency_overrides[get_favorite_repository] = lambda: FailingExistsRepository()
    try:
        with TestClient(app) as test_client:
            response = test_client.put(
                "/api/favorites/biz-503",
                headers={"X-Device-Id": "550e8400-e29b-41d4-a716-446655440000"},
                params={"business_id": target_business_id},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 503
    data = response.json()
    assert data["isSuccess"] is False
    assert data["code"] == "COMMON-001"
    assert data["result"] is None


def test_get_favorites_returns_503_when_repository_read_fails():
    class FailingGetAllRepository(MockFavoriteRepository):
        def get_all(self, device_id: str):  # noqa: ARG002
            raise FavoriteRepositoryUnavailableError("紐⑸줉 議고쉶 ?ㅽ뙣")

    app.dependency_overrides[get_favorite_repository] = lambda: FailingGetAllRepository()
    try:
        with TestClient(app) as test_client:
            response = test_client.get(
                "/api/favorites",
                headers={"X-Device-Id": "550e8400-e29b-41d4-a716-446655440000"},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 503
    data = response.json()
    assert data["isSuccess"] is False
    assert data["code"] == "COMMON-001"
    assert data["result"] is None



