import pytest
from fastapi.testclient import TestClient
from app.main import app
from unittest.mock import patch, MagicMock, AsyncMock
import asyncio
import httpx
from app.core.config import SUPABASE_URL, SUPABASE_KEY, SUPABASE_TABLE

@pytest.fixture
def client():
    return TestClient(app)

def test_ping(client):
    response = client.get("/ping")
    assert response.status_code == 200
    assert response.json() == {"ok": True}

@patch("httpx.AsyncClient")
def test_health_check_success(mock_client_class, client):
    mock_client = AsyncMock()
    mock_client_class.return_value.__aenter__.return_value = mock_client
    
    mock_response = MagicMock()
    mock_response.raise_for_status.return_value = None
    mock_client.get.return_value = mock_response

    response = client.get("/health")
    
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["dependencies"]["database"] == "ok"
    
    mock_client.get.assert_called_once_with(
        f"{SUPABASE_URL}/rest/v1/{SUPABASE_TABLE}",
        headers={
            "apikey": SUPABASE_KEY,
            "Authorization": f"Bearer {SUPABASE_KEY}"
        },
        params={"select": "id", "limit": "1"}
    )


@patch("httpx.AsyncClient")
def test_health_check_failure(mock_client_class, client):
    mock_client = AsyncMock()
    mock_client_class.return_value.__aenter__.return_value = mock_client
    
    mock_client.get.side_effect = Exception("HTTP Connection Error")

    response = client.get("/health")
    
    assert response.status_code == 503
    data = response.json()
    assert data["status"] == "degraded"
    assert data["dependencies"]["database"] == "down"

@patch("httpx.AsyncClient")
def test_health_check_timeout(mock_client_class, client):
    mock_client = AsyncMock()
    mock_client_class.return_value.__aenter__.return_value = mock_client
    
    # NOTE: httpx의 timeout 발생 상황을 정확히 모사하기 위해 
    # asyncio.TimeoutError가 아닌 httpx 예외를 사용합니다.
    mock_client.get.side_effect = httpx.ReadTimeout("timeout", request=None)

    response = client.get("/health")
    
    assert response.status_code == 503
    data = response.json()
    assert data["status"] == "degraded"
    assert data["dependencies"]["database"] == "down"
