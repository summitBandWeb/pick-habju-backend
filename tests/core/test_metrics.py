import re
import pytest
from httpx import AsyncClient
from app.main import app

@pytest.mark.asyncio
async def test_metrics_collection_success(async_client: AsyncClient):
    """
    정상적인 200 OK 응답에 대해 메트릭이 잘 쌓이는지 확인
    """
    response = await async_client.get("/ping", follow_redirects=True)
    assert response.status_code == 200
    
    # metrics 엔드포인트를 호출하여 결과를 파싱하거나 REGISTRY에서 직접 확인
    response_metrics = await async_client.get("/metrics", follow_redirects=True)
    assert response_metrics.status_code == 200
    assert re.search(r'http_requests_total\{method="GET",path="/ping",status_code="200"\} [0-9.]+', response_metrics.text)


@pytest.mark.asyncio
async def test_metrics_collection_error(async_client: AsyncClient):
    """
    에러 발생 시 상태 코드가 메트릭에 500번대로 잘 기록되는지 확인
    여기서는 존재하지 않는 라우트에 접근하여 404를 테스트하거나, 
    모의 에러 엔드포인트를 통해 500을 테스트할 수 있습니다.
    간단하게 /health 엔드포인트의 503 에러로 테스트 (Supabase Auth 키 없음 등으로 실패 유도).
    """
    # 이 테스트 환경에서는 Supabase URL/KEY가 모킹되지 않았으므로 timeout 또는 503이 발생할 확률이 높음
    response = await async_client.get("/health", follow_redirects=True)
        
    # /health는 DB 연결 실패 시 503 반환
    assert response.status_code == 503
    
    response_metrics = await async_client.get("/metrics", follow_redirects=True)
    assert response_metrics.status_code == 200
    assert re.search(r'http_requests_total\{method="GET",path="/health",status_code="503"\} [0-9.]+', response_metrics.text)
