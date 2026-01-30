from app.exception.base_exception import BaseCustomException, ErrorCode
from fastapi.responses import JSONResponse
from fastapi import Request
from datetime import datetime
import logging
from app.core.response import error_response
import traceback

logger = logging.getLogger("app")

async def custom_exception_handler(request: Request, exc: BaseCustomException):
    # 4xx/도메인 에러: 경고 수준으로 로깅
    logger.warning({
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "status": exc.status_code,
        "errorCode": exc.error_code,
        "message": exc.message,
    })
    
    # Envelope Pattern에 맞춰 ApiResponse 반환
    return JSONResponse(
        status_code=exc.status_code,
        content=error_response(
            code=exc.error_code,
            message=exc.message
        ).model_dump()
    )

async def global_exception_handler(request: Request, exc: Exception):
    # 5xx/미처리 예외: 에러 수준으로 스택 로깅
    logger.exception({
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "status": 500,
        "errorCode": ErrorCode.COMMON_INTERNAL_ERROR,
        "message": "서버 내부 오류가 발생했습니다.",
    })
    return JSONResponse(
        status_code=500,
        content={
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "status": 500,
            "errorCode": ErrorCode.COMMON_INTERNAL_ERROR,
            "message": "서버 내부 오류가 발생했습니다.",
            "stack_trace": traceback.format_exc(),
        }
    )
