from fastapi import Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi import HTTPException
from slowapi.errors import RateLimitExceeded
import logging
from app.core.response import error_response, ValidationErrorDetail
from datetime import datetime
from app.core.error_codes import ErrorCode
from app.exception.base_exception import BaseCustomException
from app.exception.common.rate_limit_exception import RateLimitException
from app.core.config import IS_DEBUG
import traceback

logger = logging.getLogger("app")


async def custom_exception_handler(request: Request, exc: BaseCustomException):
    """
    비즈니스 로직 예외(BaseCustomException)를 ApiResponse 포맷으로 변환
    
    Rationale:
        도메인 로직에서 발생한 예외를 표준 에러 응답으로 변환합니다.
        4xx 에러이므로 경고 수준으로 로깅합니다.
    """
    # error_code가 Enum이면 .value, 아니면 그대로 사용
    error_code_value = exc.error_code.value if hasattr(exc.error_code, 'value') else exc.error_code
    
    logger.warning({
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "status": exc.status_code,
        "errorCode": error_code_value,
        "message": exc.message,
        "client_ip": request.client.host,
        "path": request.url.path
    })
    return JSONResponse(
        status_code=exc.status_code,
        content=error_response(
            message=exc.message,
            code=error_code_value
        ).model_dump()
    )


async def http_exception_handler(request: Request, exc: HTTPException):
    """
    HTTPException을 ApiResponse 포맷으로 변환
    
    Rationale:
        FastAPI의 HTTPException이 발생했을 때에도 프론트엔드가
        표준 Envelope Pattern을 받도록 자동 변환합니다.
    """
    return JSONResponse(
        status_code=exc.status_code,
        content=error_response(
            message=exc.detail,
            code=ErrorCode.http_error(exc.status_code)
        ).model_dump()
    )


async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """
    Pydantic Validation Error를 ApiResponse 포맷으로 변환 (422)
    
    Rationale:
        요청 본문/쿼리 파라미터 검증 실패 시 발생하는 422 에러를
        표준 포맷으로 변환하여, 프론트엔드가 필드별 에러를 쉽게 표시할 수 있게 합니다.
    """
    error_details = {}
    for error in exc.errors():
        field = ".".join(str(loc) for loc in error["loc"])
        error_details[field] = ValidationErrorDetail(
            message=error["msg"],
            type=error["type"],
            input=error.get("input")
        )
    
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content=error_response(
            message="입력값을 확인해주세요.",
            code=ErrorCode.VALIDATION_ERROR,
            result=error_details
        ).model_dump()
    )


async def global_exception_handler_envelope(request: Request, exc: Exception):
    """
    모든 예외(500 포함)를 ApiResponse 포맷으로 변환
    
    Rationale:
        예상치 못한 서버 에러 발생 시 상세 스택 트레이스는 로그에만 기록하고,
        클라이언트에게는 일반적인 메시지만 반환하여 보안을 강화합니다.
    """
    # 상세 로그 기록 (Trace ID는 로깅 필터에서 자동으로 주입됨)
    logger.exception(
        f"Unhandled Exception: {str(exc)}",
        extra={
            "path": request.url.path,
            "method": request.method,
            "client_ip": request.client.host if request.client else None,
        }
    )
    
    # 보안 강화: 디버그 모드가 아닐 경우 상세 에러 정보(Stack Trace 등)를 노출하지 않음
    if IS_DEBUG:
        error_result = {
            "error_detail": str(exc),
            "stack_trace": traceback.format_exc()
        }
    else:
        error_result = None

    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content=error_response(
            message="서버 내부 오류가 발생했습니다. 담당자에게 문의해주세요.",
            code=ErrorCode.INTERNAL_ERROR,
            result=error_result
        ).model_dump()
    )


async def rate_limit_exception_handler(request: Request, exc: RateLimitExceeded):
    """
    Rate Limit 초과 예외 핸들러
    
    slowapi의 RateLimitExceeded 예외를 비즈니스 예외(RateLimitException)로 변환하여
    일관된 에러 응답 포맷을 유지합니다.

    Args:
        request (Request): FastAPI Request 객체
        exc (RateLimitExceeded): 발생한 Rate Limit 예외

    Returns:
        JSONResponse: 429 Too Many Requests 응답
    """
    rate_limit_exc = RateLimitException()
    return await custom_exception_handler(request, rate_limit_exc)
