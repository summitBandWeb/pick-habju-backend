
import pytest
import httpx
from unittest.mock import AsyncMock, patch, MagicMock
from app.utils.client_loader import load_client
from app.exception.api.client_loader_exception import RequestFailedError

@pytest.mark.asyncio
async def test_retry_success_after_failure():
    """503 에러 발생 시 재시도 후 성공하는지 테스트"""
    url = "https://example.com/api"

    # Mock Response 객체들 생성
    # 첫 번째: 503 에러 (raise_for_status 호출 시 에러 발생)
    fail_response = MagicMock(spec=httpx.Response)
    fail_response.status_code = 503
    fail_response.raise_for_status.side_effect = httpx.HTTPStatusError(
        "503 Service Unavailable", request=None, response=fail_response
    )

    # 두 번째: 200 성공
    success_response = MagicMock(spec=httpx.Response)
    success_response.status_code = 200
    success_response.json.return_value = {"ok": True}
    success_response.raise_for_status.return_value = None  # 성공 시 에러 없음

    # Mock Client 인스턴스 생성
    mock_client_instance = AsyncMock(spec=httpx.AsyncClient)
    # post 메서드가 호출될 때마다 순서대로 리턴 (실패 -> 성공)
    mock_client_instance.post.side_effect = [fail_response, success_response]

    # httpx.AsyncClient 클래스 생성자를 Mocking
    # load_client 내부에서 httpx.AsyncClient()를 부르면 위에서 만든 mock_client_instance가 반환됨
    with patch("httpx.AsyncClient", return_value=mock_client_instance):
        response = await load_client(url)

    # 검증
    assert response.status_code == 200
    assert mock_client_instance.post.call_count == 2  # 총 2번 호출 (1번 실패 + 1번 재시도)

@pytest.mark.asyncio
async def test_no_retry_on_404():
    """404 에러 발생 시 재시도 없이 즉시 실패하는지 테스트"""
    url = "https://example.com/api"

    # Mock Response: 404 에러
    fail_response = MagicMock(spec=httpx.Response)
    fail_response.status_code = 404
    fail_response.raise_for_status.side_effect = httpx.HTTPStatusError(
        "404 Not Found", request=None, response=fail_response
    )

    mock_client_instance = AsyncMock(spec=httpx.AsyncClient)
    mock_client_instance.post.return_value = fail_response

    with patch("httpx.AsyncClient", return_value=mock_client_instance):
        with pytest.raises(RequestFailedError):
            await load_client(url)

    # 검증
    assert mock_client_instance.post.call_count == 1  # 재시도 없이 1번만 호출되어야 함
