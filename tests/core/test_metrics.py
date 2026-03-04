import re
import pytest
from httpx import AsyncClient
from app.main import app
from unittest.mock import patch, AsyncMock
from prometheus_client import generate_latest
import httpx


@pytest.mark.asyncio
async def test_metrics_collection_success(async_client: AsyncClient):
    """
    정상적인 200 OK 응답에 대해 메트릭이 잘 쌓이는지 확인
    """
    response = await async_client.get("/ping", follow_redirects=True)
    assert response.status_code == 200
    
    # metrics 엔드포인트를 호출하여 결과를 파싱하거나 REGISTRY에서 직접 확인
    metrics_data = generate_latest().decode("utf-8")
    assert re.search(r'http_requests_total\{method="GET",path="/ping",status_code="200"\} [0-9.]+', metrics_data)

@pytest.mark.asyncio
async def test_metrics_collection_error(async_client: AsyncClient):
    """
    에러 발생 시 상태 코드가 메트릭에 500번대로 잘 기록되는지 확인
    모의 에러 엔드포인트를 통해 500/503을 테스트합니다.
    """
    with patch("app.main.get_global_client") as mock_get_global_client:
        mock_client = AsyncMock()
        mock_get_global_client.return_value = mock_client
        mock_client.get.side_effect = httpx.TimeoutException("timeout")
        
        response = await async_client.get("/health", follow_redirects=True)
            
    # 타임아웃 시 503이나 500 등이 반환됨
    assert response.status_code in (500, 503)
    
    metrics_data = generate_latest().decode("utf-8")
    assert re.search(r'http_requests_total\{method="GET",path="/health",status_code="(500|503)"\} [0-9.]+', metrics_data)
