import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.available_room import router as available_router
from app.core.config import ALLOWED_ORIGINS
from app.core.logging_config import setup_logging
from app.core.middleware import CacheControlMiddleware, RealIPMiddleware
from app.exception.base_exception import BaseCustomException
from app.exception.exception_handler import (
    custom_exception_handler,
    global_exception_handler,
)
import app.crawler  # Trigger crawler registration on startup.

ALLOWED_ORIGINS_SET = {
    "https://www.pickhabju.com",
    "https://pickhabju.com",
    # 필요시 추가
}

from contextlib import asynccontextmanager
from app.utils.client_loader import set_global_client, close_global_client


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 시작 시 클라이언트 설정
    await set_global_client()
    yield
    # 종료 시 클라이언트 정리
    await close_global_client()


app = FastAPI(lifespan=lifespan)

# CORS 설정 (환경변수 기반)
# 라우터보다 먼저 추가되어야 CORS 헤더가 올바르게 적용됩니다.
# origins = ALLOWED_ORIGINS + ["https://6w9bh0usvh.execute-api.ap-northeast-2.amazonaws.com"] # API Gateway URL 추가

origins = list(
    {
        *ALLOWED_ORIGINS,
        "https://www.pickhabju.com",
        "https://pickhabju.com",
        # 개발용 필요하면 여기에 추가:
        # "http://localhost:3000", "http://localhost:5173",
    }
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_origin_regex=r"^https:\/\/pick\-habju\-frontend.*\.vercel\.app$",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Cloud Run 최적화 미들웨어
# 1. Cache-Control: API 응답 캐시 방지 (Cloudflare와 이중 보호)
# 2. Real IP: Cloudflare 프록시 뒤 실제 클라이언트 IP 로깅
app.add_middleware(CacheControlMiddleware)
app.add_middleware(RealIPMiddleware)


@app.get("/ping")
def ping():
    return {"ok": True}


# API 라우터 포함
app.include_router(available_router)

# 커스텀 예외 핸들러는 라우터 포함 이후에 추가
app.add_exception_handler(BaseCustomException, custom_exception_handler)
app.add_exception_handler(Exception, global_exception_handler)

# 로깅 설정(콘솔 + 일자별 파일 로테이션, JSON 포맷)
setup_logging()

if __name__ == "__main__":
    uvicorn.run("main:app", port=8000, reload=True)
