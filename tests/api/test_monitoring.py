import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock, AsyncMock
from app.main import app

@pytest.fixture
def client():
    return TestClient(app)

@patch("app.api.monitoring.MONITORING_SECRET_TOKEN", "test-secret-token")
@patch("app.api.monitoring.send_discord_report", new_callable=AsyncMock)
def test_trigger_daily_report_success(mock_send_report, client):
    """
    유효한 토큰을 사용하여 요청 시 200 OK를 반환하는지 검증합니다.
    """
    mock_send_report.return_value = None
    response = client.post(
        "/api/v1/monitoring/daily-report",
        headers={"X-Monitoring-Token": "test-secret-token"}
    )
    
    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is True
    mock_send_report.assert_called_once()

@patch("app.api.monitoring.MONITORING_SECRET_TOKEN", "test-secret-token")
@patch("app.api.monitoring.send_discord_report", new_callable=AsyncMock)
def test_trigger_daily_report_forbidden(mock_send_report, client):
    """
    잘못된 토큰을 사용하거나 토큰이 없을 때 403 Forbidden을 반환하는지 검증합니다.
    """
    # 1. 잘못된 토큰
    response = client.post(
        "/api/v1/monitoring/daily-report",
        headers={"X-Monitoring-Token": "wrong-token"}
    )
    assert response.status_code == 403
    
    # 2. 토큰 누락
    response = client.post("/api/v1/monitoring/daily-report")
    assert response.status_code == 403
    
    # 내부 로직이 호출되지 않아야 함
    mock_send_report.assert_not_called()

@patch("app.api.monitoring.MONITORING_SECRET_TOKEN", "test-secret-token")
@patch("app.api.monitoring.send_discord_report", new_callable=AsyncMock)
def test_trigger_daily_report_failure(mock_send_report, client):
    """
    인증은 통과했으나 내부 전송 로직 실패 시 500 에러를 반환하는지 검증합니다.
    """
    mock_send_report.side_effect = Exception("Webhook integration failed")
    response = client.post(
        "/api/v1/monitoring/daily-report",
        headers={"X-Monitoring-Token": "test-secret-token"}
    )
    
    assert response.status_code == 500
    data = response.json()
    assert data["message"] == "Internal server error while triggering report"
    mock_send_report.assert_called_once()
