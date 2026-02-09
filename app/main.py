import uvicorn
import os
from fastapi import FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.api.available_room import router as available_router
from app.api.favorites import router as favorites_router
from app.api._dev.debug_envelope import router as demo_router
from app.core.config import ALLOWED_ORIGINS
from app.core.logging_config import setup_logging
from app.core.response import ApiResponse, error_response
from app.exception.base_exception import BaseCustomException
from slowapi.errors import RateLimitExceeded
from app.core.limiter import limiter
import app.crawler  # Trigger crawler registration on startup.

from contextlib import asynccontextmanager
from app.utils.client_loader import set_global_client, close_global_client

from app.exception.envelope_handlers import (
    http_exception_handler,
    validation_exception_handler,
    global_exception_handler_envelope,
    custom_exception_handler,
    rate_limit_exception_handler
)


ALLOWED_ORIGINS_SET = {
    "https://www.pickhabju.com",
    "https://pickhabju.com",
    # 필요시 추가
}

@asynccontextmanager
async def lifespan(app: FastAPI):
    # 시작 시 클라이언트 설정
    await set_global_client()
    yield
    # 종료 시 클라이언트 정리
    await close_global_client()

app = FastAPI(
    title="Pick 합주 API",
    description="""
## 합주실 예약 가능 여부 확인 서비스

### 주요 기능
- 합주실 룸별 예약 가능 여부 조회
- 네이버 예약 시스템 연동

### 데이터 출처
- 네이버 예약 GraphQL API (booking.naver.com)
    """,
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    lifespan=lifespan,
)

app.state.limiter = limiter

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


@app.get("/ping")
def ping():
    return {"ok": True}

# API 라우터 포함
app.include_router(available_router)
app.include_router(favorites_router)

if os.getenv("ENV") != "prod":
    app.include_router(demo_router)

# === Global Exception Handlers (Envelope Pattern 적용) ===
# FastAPI는 예외 타입의 구체성(specificity)을 기반으로 매칭하므로
# 등록 순서와 관계없이 더 구체적인 예외 핸들러가 우선 적용됩니다.
# 아래는 가독성을 위해 구체적 → 일반적 순서로 나열했습니다.

# 1. Rate Limit 예외
app.add_exception_handler(RateLimitExceeded, rate_limit_exception_handler)

# 2. 커스텀 예외 (비즈니스 로직)
app.add_exception_handler(BaseCustomException, custom_exception_handler)

# 3. 검증 예외
app.add_exception_handler(RequestValidationError, validation_exception_handler)

# 4. HTTP 예외
app.add_exception_handler(HTTPException, http_exception_handler)

# 5. 그 외 모든 예외 (서버 에러) - 가장 일반적
app.add_exception_handler(Exception, global_exception_handler_envelope)

# 로깅 설정(콘솔 + 일자별 파일 로테이션, JSON 포맷)
setup_logging()

if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        port=8000,
        reload=True
    )
