import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock, AsyncMock
from app.main import app

@pytest.fixture
def client():
    return TestClient(app)

@patch("app.api.monitoring.send_discord_report", new_callable=AsyncMock)
def test_trigger_daily_report_success(mock_send_report, client):
    """
    데일리 리포트 트리거 엔드포인트가 정상적으로 200 OK를 반환하고,
    동기적으로 `send_discord_report`를 호출하는지 검증합니다.
    """
    mock_send_report.return_value = None
    response = client.post("/api/v1/monitoring/daily-report")
    
    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is True
    assert data["message"] == "Daily report triggered successfully"
    mock_send_report.assert_called_once()

@patch("app.api.monitoring.send_discord_report", new_callable=AsyncMock)
def test_trigger_daily_report_failure(mock_send_report, client):
    """
    내부 전송 로직 실패 시 GCP 인프라에서 즉시 인지할 수 있도록 
    HTTP 500 에러를 동기적으로 반환하는지 검증합니다.
    """
    mock_send_report.side_effect = Exception("Webhook integration failed")
    response = client.post("/api/v1/monitoring/daily-report")
    
    assert response.status_code == 500
    data = response.json()
    # envelope pattern으로 인해 detail 대신 message에 에러 내용이 담김
    assert data["message"] == "Internal server error while triggering report"
    mock_send_report.assert_called_once()
