from fastapi import Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi import HTTPException
import logging
from app.core.response import error_response, ValidationErrorDetail
from datetime import datetime
from app.core.response import error_response
from app.core.error_codes import ErrorCode
from app.exception.base_exception import BaseCustomException

logger = logging.getLogger(__name__)


async def custom_exception_handler(request: Request, exc: BaseCustomException):
    """
    비즈니스 로직 예외(BaseCustomException)를 ApiResponse 포맷으로 변환
    
    Rationale:
        도메인 로직에서 발생한 예외를 표준 에러 응답으로 변환합니다.
        4xx 에러이므로 경고 수준으로 로깅합니다.
    """
    logger.warning({
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "status": exc.status_code,
        "errorCode": exc.error_code,
        "message": exc.message,
    })
    return JSONResponse(
        status_code=exc.status_code,
        content=error_response(
            message=exc.message,
            code=exc.error_code
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
        예상치 못한 서버 에러가 발생해도 프론트엔드는 항상
        isSuccess: false 형태의 JSON을 받게 됩니다.
    """
    logger.exception(
        "Unhandled Exception",
        extra={
            "path": request.url.path,
            "method": request.method,
            "client": request.client.host if request.client else None
        }
    )
    
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content=error_response(
            message="서버 내부 오류가 발생했습니다.",
            code=ErrorCode.INTERNAL_ERROR
        ).model_dump()
    )
