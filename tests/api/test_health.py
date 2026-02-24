import pytest
from fastapi.testclient import TestClient
from app.main import app
from unittest.mock import patch, MagicMock, AsyncMock
import asyncio
import httpx

client = TestClient(app)

def test_ping():
    response = client.get("/ping")
    assert response.status_code == 200
    assert response.json() == {"ok": True}

@patch("httpx.AsyncClient")
def test_health_check_success(mock_client_class):
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


@patch("httpx.AsyncClient")
def test_health_check_failure(mock_client_class):
    mock_client = AsyncMock()
    mock_client_class.return_value.__aenter__.return_value = mock_client
    
    mock_client.get.side_effect = Exception("HTTP Connection Error")

    response = client.get("/health")
    
    assert response.status_code == 503
    data = response.json()
    assert data["status"] == "degraded"
    assert data["dependencies"]["database"] == "down"

@patch("httpx.AsyncClient")
def test_health_check_timeout(mock_client_class):
    mock_client = AsyncMock()
    mock_client_class.return_value.__aenter__.return_value = mock_client
    
    mock_client.get.side_effect = asyncio.TimeoutError()

    response = client.get("/health")
    
    assert response.status_code == 503
    data = response.json()
    assert data["status"] == "degraded"
    assert data["dependencies"]["database"] == "down"
