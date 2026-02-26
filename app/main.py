import os
import asyncio
import logging
from contextlib import asynccontextmanager

logger = logging.getLogger(__name__)

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from slowapi.errors import RateLimitExceeded
import app.crawler

from app.api.available_room import router as available_router
from app.api.favorites import router as favorites_router
from app.api._dev.debug_envelope import router as demo_router
from app.core.config import ALLOWED_ORIGINS, CORS_ORIGIN_REGEX
from app.core.limiter import limiter
from app.core.logging_config import setup_logging
from app.core.middleware import CacheControlMiddleware, RealIPMiddleware, TraceIDMiddleware
from app.exception.base_exception import BaseCustomException
from app.exception.envelope_handlers import (
    custom_exception_handler,
    global_exception_handler_envelope,
    http_exception_handler,
    rate_limit_exception_handler,
    validation_exception_handler,
)
from app.utils.client_loader import close_global_client, set_global_client
from app.core.supabase_client import get_supabase_client
from pydantic import ValidationError
import httpx
from app.core.config import SUPABASE_URL, SUPABASE_KEY, HEALTH_CHECK_TIMEOUT
from app.models.dto import HealthResponse

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
    version="2.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    lifespan=lifespan,
)

app.state.limiter = limiter

# CORS 설정 (환경변수 기반)
# 라우터보다 먼저 추가되어야 CORS 헤더가 올바르게 적용됩니다.
# ALLOWED_ORIGINS는 config.py에서 환경변수 기반으로 구성됩니다.

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_origin_regex=CORS_ORIGIN_REGEX,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 미들웨어 설정 (FastAPI는 LIFO: 마지막에 추가된 것이 가장 먼저 실행됨)
# 따라서 아래에서 위로 읽으면 실제 실행 순서와 일치합니다.
# INNERMOST (실행 순서 3) -> Real IP: 실제 IP 추출 및 요청 정보 로깅
# MIDDLE    (실행 순서 2) -> Cache-Control: API 응답 캐시 방지
# OUTERMOST (실행 순서 1) -> Trace ID: 모든 요청에 고유 ID 부여 및 로깅 컨텍스트 설정
app.add_middleware(RealIPMiddleware)
app.add_middleware(CacheControlMiddleware)
app.add_middleware(TraceIDMiddleware)


@app.get("/ping")
def ping():
    return {"ok": True}

@app.get("/health", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    """
    인프라 기반 readiness 체크 엔드포인트
    DB 등 핵심 의존성의 상태를 점검합니다. 
    장애 시 503 상태 코드를 반환하여 로드밸런서가 트래픽을 차단(비정상 상태 식별)할 수 있도록 합니다.
    
    NOTE: 
    DB 일시 장애 시 앱 컨테이너까지 연쇄 재시작되는 현상(Restart loop) 및 Cold start 비용을 
    방지하기 위해, 컨테이너의 생존 여부(Liveness)는 /ping 엔드포인트를 사용하도록 분리되었습니다. 
    해당 /health 엔드포인트는 트래픽 수신 가능 여부(Readiness) 판단에만 사용해야 합니다.
    """
    health_status = {"status": "healthy", "dependencies": {"database": "ok"}}
    try:        
        # 설정된 타임아웃(기본 2.0초) 제한으로 Supabase REST API 테이블 조회를 통해 실제 DB 연결 상태 점검
        async with httpx.AsyncClient(timeout=HEALTH_CHECK_TIMEOUT) as client:
            # PostgREST 루트 조회(/rest/v1/)는 DB가 다운되어도 캐시를 통해 200을 
            # 반환할 수 있으므로, 실제 테이블의 레코드 조회를 통해 연결성을 검증
            response = await client.get(
                f"{SUPABASE_URL}/rest/v1/favorites?select=id&limit=1",
                headers={
                    "apikey": SUPABASE_KEY,
                    "Authorization": f"Bearer {SUPABASE_KEY}"
                }
            )
            response.raise_for_status()
    except Exception:  # noqa: BLE001
        logger.error("Health check failed", exc_info=True)
        health_status["status"] = "degraded"
        health_status["dependencies"]["database"] = "down"
        error_response = HealthResponse(**health_status)
        return JSONResponse(status_code=503, content=error_response.model_dump())
    return HealthResponse(**health_status)


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
app.add_exception_handler(ValidationError, validation_exception_handler)

# 4. HTTP 예외
app.add_exception_handler(HTTPException, http_exception_handler)

# 5. 그 외 모든 예외 (서버 에러) - 가장 일반적
app.add_exception_handler(Exception, global_exception_handler_envelope)

# 로깅 설정(콘솔 + 일자별 파일 로테이션, JSON 포맷)
setup_logging()

if __name__ == "__main__":
    uvicorn.run("main:app", port=8000, reload=True)
