from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api.available_room import router as available_router
from app.exception.base_exception import BaseCustomException
from app.exception.exception_handler import custom_exception_handler, global_exception_handler
from app.core.logging_config import setup_logging
from app.core.config import ALLOWED_ORIGINS
import httpx
from contextlib import asynccontextmanager

REQUEST_TIMEOUT = httpx.Timeout(connect=5.0, read=10.0, write=10.0, pool=5.0)
HTTP_LIMITS = httpx.Limits(max_connections=100, max_keepalive_connections=20, keepalive_expiry=30.0)
DEFAULT_HEADERS = {"User-Agent": "PickHabju/1.0"}

@asynccontextmanager
async def lifespan(app: FastAPI) -> "AsyncGenerator[None, None]":
    app.state.http = httpx.AsyncClient(
        timeout=REQUEST_TIMEOUT,
        limits=HTTP_LIMITS,
        headers=DEFAULT_HEADERS,
        follow_redirects=True,
        http2=True,
    )
    try:
        yield
    finally:
        await app.state.http.aclose()

app = FastAPI()
@app.get("/ping")
def ping():
    return {"ok": True}

# CORS 설정 (환경변수 기반)
# 라우터보다 먼저 추가되어야 CORS 헤더가 올바르게 적용됩니다.
# origins = ALLOWED_ORIGINS + ["https://6w9bh0usvh.execute-api.ap-northeast-2.amazonaws.com"] # API Gateway URL 추가

origins = list({
    *ALLOWED_ORIGINS,
    "https://www.pickhabju.com",
    "https://pickhabju.com",
    # 개발용 필요하면 여기에 추가:
    # "http://localhost:3000", "http://localhost:5173",
})

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_origin_regex=r"^https:\/\/pick\-habju\-frontend.*\.vercel\.app$",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# API 라우터 포함
app.include_router(available_router)

# 커스텀 예외 핸들러는 라우터 포함 이후에 추가
app.add_exception_handler(BaseCustomException, custom_exception_handler)
app.add_exception_handler(Exception, global_exception_handler)

# 로깅 설정(콘솔 + 일자별 파일 로테이션, JSON 포맷)
setup_logging()
