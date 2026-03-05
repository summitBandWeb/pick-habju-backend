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
    """정상적인 헬스체크 응답을 검증합니다.
    
    Args:
        mock_get_global_client (MagicMock): 전역 클라이언트 인스턴스를 반환하는 mock 객체
        client (TestClient): FastAPI 테스트 클라이언트
        
    Rationale:
        의존하는 서비스(Supabase)와 정상적으로 통신되었을 때 `status`와 `dependencies`가 
        제대로 반환되는지 확인하기 위함입니다. `get_global_client`를 mock함으로써 
        불필요한 네트워크 연결을 방지합니다.
    """
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
def test_health_check_failure_network(mock_get_global_client, client, caplog):
    """네트워크 오류 시 헬스체크 동작을 검증합니다.
    
    Args:
        mock_get_global_client (MagicMock): 전역 클라이언트 인스턴스를 반환하는 mock 객체
        client (TestClient): FastAPI 테스트 클라이언트
        caplog: 로그 출력을 캡처하는 pytest fixture
        
    Rationale:
        단순 타임아웃이 아닌, DNS 실패나 연결 거부 등 네트워크 레벨의 `httpx.RequestError` 
        발생 시 이를 포착하여 503 오류로 우아하게 대응하는지 확인하기 위해서입니다. 
        이는 향후 인프라 모니터링 시망의 연결 신뢰도를 평가하는 지표로 사용됩니다.
    """
    mock_client = AsyncMock()
    mock_get_global_client.return_value = mock_client
    
    mock_client.get.side_effect = httpx.RequestError("HTTP Connection Error", request=MagicMock())

    response = client.get("/health")
    
    assert response.status_code == 503
    data = response.json()
    assert data["status"] == "degraded"
    assert data["dependencies"]["database"] == "down"
    assert "Network/Request error" in caplog.text

@patch("app.main.get_global_client")
def test_health_check_failure_auth_401(mock_get_global_client, client, caplog):
    """권한 인증오류(401)에 대한 헬스체크 동작을 검증합니다.
    
    Args:
        mock_get_global_client (MagicMock): 전역 클라이언트 인스턴스를 반환하는 mock 객체
        client (TestClient): FastAPI 테스트 클라이언트
        caplog: 로그 출력을 캡처하는 pytest fixture
        
    Rationale:
        잘못된 인증 정보(예: `SUPABASE_KEY` 설정 오류)로 인해 DB에서 401(Unauthorized)이 
        발생할 때, "Invalid API key"라는 명확한 로그가 남는지 확인합니다.
    """
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
    assert "Invalid API key" in caplog.text

@patch("app.main.get_global_client")
def test_health_check_failure_auth_404(mock_get_global_client, client, caplog):
    """테이블 미존재 오류(404)에 대한 헬스체크 동작을 검증합니다.
    
    Args:
        mock_get_global_client (MagicMock): 전역 클라이언트 인스턴스를 반환하는 mock 객체
        client (TestClient): FastAPI 테스트 클라이언트
        caplog: 로그 출력을 캡처하는 pytest fixture
        
    Rationale:
        잘못된 테이블 설정(예: `SUPABASE_TABLE` 설정 오류)으로 인해 DB에서 404(Not Found)가 
        발생할 때, "Table not found"라는 명확한 로그가 남는지 확인합니다.
    """
    mock_client = AsyncMock()
    mock_get_global_client.return_value = mock_client
    
    mock_response = MagicMock()
    mock_response.status_code = 404
    mock_client.get.side_effect = httpx.HTTPStatusError("Not Found", request=MagicMock(), response=mock_response)

    response = client.get("/health")
    
    assert response.status_code == 503
    data = response.json()
    assert data["status"] == "unhealthy"
    assert data["dependencies"]["database"] == "unauthorized_or_not_found"
    assert "Table not found" in caplog.text
    
@patch("app.main.get_global_client")
def test_health_check_timeout(mock_get_global_client, client, caplog):
    """타임아웃 발생 시 헬스체크 동작여부를 검증합니다.
    
    Args:
        mock_get_global_client (MagicMock): 전역 클라이언트 인스턴스를 반환하는 mock 객체
        client (TestClient): FastAPI 테스트 클라이언트
        caplog: 로그 출력을 캡처하는 pytest fixture
        
    Rationale:
        물리적인 응답 지연이 서버의 임계치(timeout)를 초과하는 상황이 
        발생해도, 전체 어플리케이션이 크래시되지 않고 상태코드 503과 함께 'degraded'를 
        안전하게 반환하는지 보장하기 위함입니다.
    """
    mock_client = AsyncMock()
    mock_get_global_client.return_value = mock_client
    
    mock_client.get.side_effect = httpx.ReadTimeout("Request timed out", request=MagicMock())

    response = client.get("/health")
    
    assert response.status_code == 503
    data = response.json()
    assert data["status"] == "degraded"
    assert data["dependencies"]["database"] == "down"
    assert "Supabase DB query took too long" in caplog.text

@patch("app.main.get_global_client")
def test_health_check_pool_timeout(mock_get_global_client, client, caplog):
    """커넥션 풀 고갈(PoolTimeout) 발생 시 헬스체크 동작여부를 검증합니다.
    
    Args:
        mock_get_global_client (MagicMock): 전역 클라이언트 인스턴스를 반환하는 mock 객체
        client (TestClient): FastAPI 테스트 클라이언트
        caplog: 로그 출력을 캡처하는 pytest fixture
        
    Rationale:
        커넥션 풀이 고갈되어 대기 시간 초과(PoolTimeout)가 발생하는 상황에서 
        이를 네트워크 지연(ReadTimeout)과 구분하여 "Connection pool exhausted" 오류 메시지를 
        로그로 남기는지 검증합니다.
    """
    mock_client = AsyncMock()
    mock_get_global_client.return_value = mock_client
    
    mock_client.get.side_effect = httpx.PoolTimeout("Pool timeout", request=MagicMock())

    response = client.get("/health")
    
    assert response.status_code == 503
    data = response.json()
    assert data["status"] == "degraded"
    assert data["dependencies"]["database"] == "down"
    assert "Connection pool exhausted" in caplog.text

@patch("app.main.httpx.AsyncClient", autospec=True)
@patch("app.main.get_global_client", return_value=None)
def test_health_check_fallback_client_used(mock_get_global_client, mock_async_client_cls, client):
    """전역 클라이언트 미초기화 시 폴백 클라이언트가 사용되고 정상 종료되는지 검증합니다.
    
    Args:
        mock_get_global_client (MagicMock): None을 반환하도록 설정된 mock 객체
        mock_async_client_cls (MagicMock): httpx.AsyncClient 생성자를 모방하는 mock 객체
        client (TestClient): FastAPI 테스트 클라이언트
        
    Rationale:
        테스트 환경 등에서 전역 클라이언트 리소스가 생성되지 않았을 때, 헬스체크가 
        단일 요청용 임시(fallback) 클라이언트를 자동 생성하여 안전하게 사용한 뒤 
        `aclose()`로 명확히 자원을 반납하는지 검증합니다. (Connection/Socket 고갈 방지)
    """
    mock_fallback = AsyncMock()
    mock_async_client_cls.return_value = mock_fallback
    
    mock_response = MagicMock()
    mock_response.raise_for_status.return_value = None
    mock_fallback.get.return_value = mock_response
    
    response = client.get("/health")
    
    assert response.status_code == 200
    mock_fallback.aclose.assert_called_once()  # 폴백 클라이언트 명시적 종료 검증
