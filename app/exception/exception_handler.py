from app.exception.base_exception import BaseCustomException
from fastapi.responses import JSONResponse
from fastapi import Request
from datetime import datetime
from slowapi.errors import RateLimitExceeded
from app.exception.common.rate_limit_exception import RateLimitException
import logging

logger = logging.getLogger("app")

async def custom_exception_handler(request: Request, exc: BaseCustomException):
    # 4xx/도메인 에러: 경고 수준으로 로깅(스택트레이스는 불필요)
    logger.warning({
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "status": exc.status_code,
        "errorCode": exc.error_code,
        "message": exc.message,
        "client_ip": request.client.host,
        "path": str(request.url),
    })
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "status": exc.status_code,
            "errorCode": exc.error_code,
            "message": exc.message
        }
    )

async def global_exception_handler(request: Request, exc: Exception):
    # 5xx/미처리 예외: 에러 수준으로 스택 로깅
    logger.exception({
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "status": 500,
        "errorCode": "Common-001",
        "message": "서버 내부 오류가 발생했습니다.",
    })
    return JSONResponse(
        status_code=500,
        content={
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "status": 500,
            "errorCode": "Common-001",
            "message": "서버 내부 오류가 발생했습니다."
        }
    )


async def rate_limit_exception_handler(request: Request, exc: RateLimitExceeded):
    # RateLimitException 인스턴스를 생성해서 custom_exception_handler 재사용
    rate_limit_exc = RateLimitException()
    return await custom_exception_handler(request, rate_limit_exc)
    