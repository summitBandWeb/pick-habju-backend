from fastapi import FastAPI
from app.api.available_room import router as available_router
from app.exception.base_exception import BaseCustomException
from app.exception.exception_handler import custom_exception_handler, global_exception_handler
from app.core.logging_config import setup_logging

app = FastAPI()
app.include_router(available_router)

app.add_exception_handler(BaseCustomException, custom_exception_handler)
app.add_exception_handler(Exception, global_exception_handler)

# 로깅 설정(콘솔 + 일자별 파일 로테이션, JSON 포맷)
setup_logging()
