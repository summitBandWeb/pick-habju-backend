from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api.available_room import router as available_router
from app.exception.base_exception import BaseCustomException
from app.exception.exception_handler import custom_exception_handler

app = FastAPI()
app.include_router(available_router)

app.add_exception_handler(BaseCustomException, custom_exception_handler)

# CORS 설정 (로컬 프론트엔드용)
origins = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "http://localhost:5173",
    "http://127.0.0.1:5173",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
