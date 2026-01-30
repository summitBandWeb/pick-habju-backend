import pytest
from unittest.mock import patch, MagicMock
from fastapi import Request, HTTPException
from app.exception.envelope_handlers import global_exception_handler_envelope as global_exception_handler, custom_exception_handler
from app.exception.base_exception import BaseCustomException, ErrorCode
from app.core.response import ApiResponse

# Test Custom Exception
class TestCustomException(BaseCustomException):
    def __init__(self):
        super().__init__(
            message="Test Error",
            error_code=ErrorCode.COMMON_BAD_REQUEST,
            status_code=400
        )

@pytest.mark.asyncio
async def test_custom_exception_handler_structure():
    """
    BaseCustomException 발생 시 ApiResponse 포맷(JSON)으로 응답하는지 검증
    """
    exc = TestCustomException()
    request = MagicMock(spec=Request)
    request.url.path = "/test"

    response = await custom_exception_handler(request, exc)
    
    assert response.status_code == 400
    
    # Body parsing
    import json
    body = json.loads(response.body)
    
    assert body["isSuccess"] is False
    assert body["code"] == "COMMON-002"
    assert body["message"] == "Test Error"
    assert body["result"] is None

@pytest.mark.asyncio
async def test_global_exception_handler_structure_prod():
    """
    운영 환경(IS_DEBUG=False)에서 500 에러 발생 시 스택 트레이스가 숨겨지는지 검증
    """
    exc = Exception("Unexpected Server Error")
    request = MagicMock(spec=Request)
    request.url.path = "/test"

    # Patch IS_DEBUG in the handler module
    with patch("app.exception.envelope_handlers.IS_DEBUG", False):
        response = await global_exception_handler(request, exc)

        assert response.status_code == 500
        
        import json
        body = json.loads(response.body)
        
        assert body["isSuccess"] is False
        assert body["code"] == "COMMON-001"
        # Result should be None or not contain stack_trace
        if body["result"]:
            assert "stack_trace" not in body["result"]
        else:
            assert body["result"] is None

@pytest.mark.asyncio
async def test_global_exception_handler_structure_dev():
    """
    개발 환경(IS_DEBUG=True)에서 500 에러 발생 시 스택 트레이스가 포함되는지 검증
    """
    exc = Exception("Unexpected Server Error")
    request = MagicMock(spec=Request)
    request.url.path = "/test"

    # Patch IS_DEBUG in the handler module
    with patch("app.exception.envelope_handlers.IS_DEBUG", True):
        response = await global_exception_handler(request, exc)

        assert response.status_code == 500
        
        import json
        body = json.loads(response.body)
        
        assert body["result"] is not None
        assert "stack_trace" in body["result"]
        assert "error_detail" in body["result"]
        assert body["result"]["error_detail"] == "Unexpected Server Error"
