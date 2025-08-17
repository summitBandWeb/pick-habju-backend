from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api.available_room import router as available_router
from app.exception.base_exception import BaseCustomException
from app.exception.exception_handler import custom_exception_handler
from app.core.config import ALLOWED_ORIGINS

app = FastAPI()

# CORS 설정 (환경변수 기반)
# 라우터보다 먼저 추가되어야 CORS 헤더가 올바르게 적용됩니다.
origins = ALLOWED_ORIGINS

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# API 라우터 포함
app.include_router(available_router)

# 커스텀 예외 핸들러는 라우터 포함 이후에 추가
app.add_exception_handler(BaseCustomException, custom_exception_handler)

