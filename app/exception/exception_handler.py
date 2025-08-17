import app

from app.exception.base_exception import BaseCustomException
from fastapi.responses import JSONResponse
from fastapi import Request
from datetime import datetime

async def custom_exception_handler(request: Request, exc: BaseCustomException):
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "status": exc.status_code,
            "errorCode": exc.error_code,
            "message": exc.message
        }
    )
