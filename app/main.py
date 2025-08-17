from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api.available_room import router as available_router
from app.exception.base_exception import BaseCustomException
from app.exception.exception_handler import custom_exception_handler
from app.core.config import ALLOWED_ORIGINS

app = FastAPI()
app.include_router(available_router)

app.add_exception_handler(BaseCustomException, custom_exception_handler)

# CORS 설정 (환경변수 기반)
origins = ALLOWED_ORIGINS

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
