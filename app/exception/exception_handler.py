from fastapi.responses import JSONResponse
from fastapi import Request
from datetime import datetime
import logging
import traceback

from app.core.config import IS_DEBUG
from app.core.response import ApiResponse, error_response
from app.exception.base_exception import BaseCustomException, ErrorCode

logger = logging.getLogger("app")


async def custom_exception_handler(request: Request, exc: BaseCustomException):
    """
    커스텀 예외 처리 핸들러 (4xx, 도메인 에러)
    """
    # 경고 수준 로깅 (스택 트레이스 불필요)
    logger.warning({
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "status": exc.status_code,
        "errorCode": exc.error_code.value,  # Enum value 사용
        "message": exc.message,
        "path": request.url.path
    })
    
    # Envelope Pattern에 맞춰 ApiResponse 반환
    return JSONResponse(
        status_code=exc.status_code,
        content=error_response(
            code=exc.error_code.value,
            message=exc.message
        ).model_dump()
    )


async def global_exception_handler(request: Request, exc: Exception):
    """
    전역 예외 처리 핸들러 (5xx, 미처리 예외)
    """
    error_msg = str(exc)
    stack_trace = traceback.format_exc()

    # 에러 수준 로깅 (항상 스택 트레이스 포함하여 서버 로그에 남김)
    logger.exception({
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "status": 500,
        "errorCode": ErrorCode.COMMON_INTERNAL_ERROR.value,
        "message": "서버 내부 오류가 발생했습니다.",
        "detail": error_msg,
        "path": request.url.path
    })

    # 응답 생성
    response_content = error_response(
        code=ErrorCode.COMMON_INTERNAL_ERROR.value,
        message="서버 내부 오류가 발생했습니다."
    ).model_dump()

    # 개발 환경(IS_DEBUG=True)인 경우에만 스택 트레이스 포함
    if IS_DEBUG:
        response_content["result"] = {
            "error_detail": error_msg,
            "stack_trace": stack_trace
        }

    return JSONResponse(
        status_code=500,
        content=response_content
    )
