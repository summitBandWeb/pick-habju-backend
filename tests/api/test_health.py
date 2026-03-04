import pytest
from fastapi.testclient import TestClient
from app.main import app
from unittest.mock import patch, MagicMock, AsyncMock
import asyncio
import httpx
from app.core.config import SUPABASE_URL, SUPABASE_KEY, SUPABASE_TABLE, HEALTH_CHECK_TIMEOUT

@pytest.fixture
def client():
    return TestClient(app)

def test_ping(client):
    response = client.get("/ping")
    assert response.status_code == 200
    assert response.json() == {"ok": True}

@patch("app.main.get_global_client")
def test_health_check_success(mock_get_global_client, client):
    mock_client = AsyncMock()
    mock_get_global_client.return_value = mock_client
    
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
        params={"select": "id", "limit": "1"},
        timeout=HEALTH_CHECK_TIMEOUT
    )

@patch("app.main.get_global_client")
def test_health_check_failure_network(mock_get_global_client, client):
    mock_client = AsyncMock()
    mock_get_global_client.return_value = mock_client
    
    mock_client.get.side_effect = httpx.RequestError("HTTP Connection Error", request=MagicMock())

    response = client.get("/health")
    
    assert response.status_code == 503
    data = response.json()
    assert data["status"] == "degraded"
    assert data["dependencies"]["database"] == "down"

@patch("app.main.get_global_client")
def test_health_check_failure_auth(mock_get_global_client, client):
    mock_client = AsyncMock()
    mock_get_global_client.return_value = mock_client
    
    mock_response = MagicMock()
    mock_response.status_code = 401
    mock_client.get.side_effect = httpx.HTTPStatusError("Unauthorized", request=MagicMock(), response=mock_response)

    response = client.get("/health")
    
    assert response.status_code == 503
    data = response.json()
    assert data["status"] == "unhealthy"
    assert data["dependencies"]["database"] == "unauthorized_or_not_found"

@patch("app.main.get_global_client")
def test_health_check_timeout(mock_get_global_client, client):
    mock_client = AsyncMock()
    mock_get_global_client.return_value = mock_client
    
    mock_client.get.side_effect = httpx.ReadTimeout("Request timed out", request=MagicMock())

    response = client.get("/health")
    
    assert response.status_code == 503
    data = response.json()
    assert data["status"] == "degraded"
    assert data["dependencies"]["database"] == "down"
