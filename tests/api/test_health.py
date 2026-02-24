import pytest
from fastapi.testclient import TestClient
from app.main import app
from unittest.mock import patch, MagicMock
import asyncio

client = TestClient(app)

def test_ping():
    response = client.get("/ping")
    assert response.status_code == 200
    assert response.json() == {"ok": True}

@patch("app.main.get_supabase_client")
def test_health_check_success(mock_get_client):
    mock_supabase = MagicMock()
    mock_get_client.return_value = mock_supabase
    
    # Mocking the synchronous execute call
    mock_execute = MagicMock(return_value={"data": [{"id": 1}]})
    mock_supabase.table.return_value.select.return_value.limit.return_value.execute = mock_execute

    response = client.get("/health")
    
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["dependencies"]["database"] == "ok"


@patch("app.main.get_supabase_client")
def test_health_check_failure(mock_get_client):
    mock_supabase = MagicMock()
    mock_get_client.return_value = mock_supabase
    
    # Mocking the execute call to raise an exception
    mock_supabase.table.return_value.select.return_value.limit.return_value.execute.side_effect = Exception("DB Connection Error")

    response = client.get("/health")
    
    assert response.status_code == 503
    data = response.json()
    assert data["status"] == "degraded"
    assert data["dependencies"]["database"] == "down"

@patch("app.main.get_supabase_client")
def test_health_check_timeout(mock_get_client):
    mock_supabase = MagicMock()
    mock_get_client.return_value = mock_supabase
    
    # Mocking the execute call to simulate a timeout error from asyncio.wait_for
    mock_supabase.table.return_value.select.return_value.limit.return_value.execute.side_effect = asyncio.TimeoutError()

    response = client.get("/health")
    
    assert response.status_code == 503
    data = response.json()
    assert data["status"] == "degraded"
    assert data["dependencies"]["database"] == "down"
