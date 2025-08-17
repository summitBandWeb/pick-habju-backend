from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware # 이 부분을 추가해야 합니다.
from app.api.available_room import router as available_router
from app.exception.base_exception import BaseCustomException
from app.exception.exception_handler import custom_exception_handler

app = FastAPI()

# CORS 설정 추가
origins = [
    "https://6w9bh0usvh.execute-api.ap-northeast-2.amazonaws.com", # API Gateway 호출 URL
    # 필요한 다른 도메인 추가
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],  # 모든 HTTP 메서드 허용 (GET, POST 등)
    allow_headers=["*"],  # 모든 HTTP 헤더 허용
)

app.include_router(available_router)
app.add_exception_handler(BaseCustomException, custom_exception_handler)