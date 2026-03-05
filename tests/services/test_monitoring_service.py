import pytest
import datetime
from unittest.mock import patch, MagicMock, AsyncMock
from app.services.monitoring_service import send_discord_report, snapshot_store, MonitoringReportStatus
from httpx import HTTPStatusError, Request, Response

@pytest.fixture
def mock_snapshot_store():
    with patch("app.services.monitoring_service.snapshot_store.acquire_lock", new_callable=AsyncMock) as mock_acquire, \
         patch("app.services.monitoring_service.snapshot_store.release_lock", new_callable=AsyncMock) as mock_release, \
         patch("app.services.monitoring_service.snapshot_store.load_snapshot", new_callable=AsyncMock) as mock_load, \
         patch("app.services.monitoring_service.snapshot_store.save_snapshot", new_callable=AsyncMock) as mock_save:
         
        mock_acquire.return_value = True
        mock_load.return_value = {"total_requests": 100, "total_errors": 5, "total_duration": 10.0}
        
        yield {
            "acquire": mock_acquire,
            "release": mock_release,
            "load": mock_load,
            "save": mock_save,
        }

@pytest.mark.asyncio
@patch("app.services.monitoring_service.DISCORD_WEBHOOK_URL", "http://test-webhook.url")
@patch("app.services.monitoring_service.httpx.AsyncClient")
@patch("app.services.monitoring_service.REGISTRY")
async def test_send_discord_report_success(mock_registry, mock_async_client_cls, mock_snapshot_store):
    """
    모니터링 리포트의 지표 파싱, 델타치 계산, 웹훅 발송을 포괄적으로 검증합니다.
    """
    # 1. Prometheus Registry Mocking
    mock_metric = MagicMock()
    mock_metric.name = "http_requests_total"
    
    mock_sample1 = MagicMock()
    mock_sample1.labels = {"path": "/health", "status_code": "200"}
    mock_sample1.value = 150  # 델타 = 150 - 100 = 50 성공 호출 추가
    mock_sample1.name = "http_requests_total"
    
    mock_sample2 = MagicMock()
    mock_sample2.labels = {"path": "/health", "status_code": "503"}
    mock_sample2.value = 7    # 델타 = 7 - 5 = 2 발생 에러 추가
    mock_sample2.name = "http_requests_total"
    
    mock_sample3 = MagicMock()
    mock_sample3.name = "http_request_duration_seconds_sum"
    mock_sample3.labels = {"path": "/health"}
    mock_sample3.value = 15.0 # 델타 = 15.0 - 10.0 = 5.0 추가 듀레이션
    
    mock_metric.samples = [mock_sample1, mock_sample2, mock_sample3]
    mock_registry.collect.return_value = [mock_metric]
    
    # 2. AsyncClient 및 Response Mocking
    mock_client = AsyncMock()
    mock_client.__aenter__.return_value = mock_client
    
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.raise_for_status = MagicMock() # no-op for success
    mock_client.post.return_value = mock_response
    
    mock_async_client_cls.return_value = mock_client
    
    # 3. 비즈니스 로직 실행
    result = await send_discord_report()
    assert result == MonitoringReportStatus.SUCCESS
    
    # 4. 검증: 분산락 로직 실행 여부
    mock_snapshot_store["acquire"].assert_called_once_with("daily_discord_report_lock")
    mock_snapshot_store["load"].assert_called_once()
    mock_snapshot_store["save"].assert_called_once_with({
        "total_requests": 157, 
        "total_errors": 7, 
        "total_duration": 15.0
    })
    mock_snapshot_store["release"].assert_called_once_with("daily_discord_report_lock")

    # 5. 검증: 메시지 구조 및 HTTP 호출
    mock_client.post.assert_called_once()
    args, kwargs = mock_client.post.call_args
    assert args[0] == "http://test-webhook.url"
    
    payload = kwargs["json"]
    assert "embeds" in payload
    embed = payload["embeds"][0]
    assert embed["title"].startswith("📊 픽합주 헬스체크 모니터링 리포트")
    
    fields = embed["fields"]
    # Total requests delta = 57, Total errors delta = 2
    assert fields[0]["value"] == "55 / 57"  # 성공 횟수 / 전체 횟수
    assert fields[1]["value"] == "2회"      # 50x 에러

@pytest.mark.asyncio
@patch("app.services.monitoring_service.DISCORD_WEBHOOK_URL", "")
async def test_send_discord_report_skip_no_webhook(mock_snapshot_store):
    """
    DISCORD_WEBHOOK_URL이 정의되지 않은 경우 스킵하는지 검증합니다.
    """
    result = await send_discord_report()
    assert result == MonitoringReportStatus.MISSING_CONFIG
    # 락 획득 시도를 안해야합니다
    mock_snapshot_store["acquire"].assert_not_called()

@pytest.mark.asyncio
@patch("app.services.monitoring_service.DISCORD_WEBHOOK_URL", "http://test")
async def test_send_discord_report_locked(mock_snapshot_store):
    """
    분산락을 획득하지 못했을 경우 프로세스를 중단하는지 검증합니다.
    """
    # 락 획득 실패 모의
    mock_snapshot_store["acquire"].return_value = False
    
    result = await send_discord_report()
    assert result == MonitoringReportStatus.SKIPPED_LOCK
    
    # 락 획득 시도는 수행했지만
    mock_snapshot_store["acquire"].assert_called_once()
    # 그 후의 로직(로드, 저장 등)은 진행되지 않아야 합니다
    mock_snapshot_store["load"].assert_not_called()
    mock_snapshot_store["save"].assert_not_called()

@pytest.mark.asyncio
@patch("app.services.monitoring_service.DISCORD_WEBHOOK_URL", "http://test")
@patch("app.services.monitoring_service.httpx.AsyncClient")
@patch("app.services.monitoring_service.REGISTRY")
async def test_send_discord_report_error_propagation(mock_registry, mock_async_client_cls, mock_snapshot_store):
    """
    HTTP 에러 발생 시 예외를 다시 던지고(re-raise), 락이 정상적으로 해제되는지 검증합니다.
    """
    # 1. Prometheus Registry Mocking (최소 데이터)
    mock_metric = MagicMock()
    mock_metric.samples = []
    mock_registry.collect.return_value = [mock_metric]
    
    # 2. AsyncClient Mocking - HTTPStatusError 유도
    mock_client = AsyncMock()
    mock_client.__aenter__.return_value = mock_client
    
    mock_response = MagicMock()
    mock_response.status_code = 500
    # raise_for_status 호출 시 httpx.HTTPStatusError 시뮬레이션
    
    request = Request("POST", "http://test")
    response = Response(500, request=request)
    mock_response.raise_for_status.side_effect = HTTPStatusError("Internal Server Error", request=request, response=response)
    
    mock_client.post.return_value = mock_response
    mock_async_client_cls.return_value = mock_client
    
    # 3. 실행 및 검증
    with pytest.raises(HTTPStatusError):
        await send_discord_report()
        
    # 4. 락이 반드시 해제되었는지 확인 (finally 블록 검증)
    mock_snapshot_store["release"].assert_called_once_with("daily_discord_report_lock")
