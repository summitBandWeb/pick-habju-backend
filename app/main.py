from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api.available_room import router as available_router
from app.exception.base_exception import BaseCustomException
from app.exception.exception_handler import custom_exception_handler, global_exception_handler
from app.core.logging_config import setup_logging
from app.core.config import ALLOWED_ORIGINS
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

ALLOWED_ORIGINS_SET = {
    "https://www.pickhabju.com",
    "https://pickhabju.com",
    # 필요시 추가
}

class PreflightMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        if request.method == "OPTIONS":
            origin = request.headers.get("origin", "")
            allow_origin = origin if origin in ALLOWED_ORIGINS_SET else ""
            headers = {
                "Access-Control-Allow-Origin": allow_origin,
                "Access-Control-Allow-Methods": "GET,POST,PUT,PATCH,DELETE,OPTIONS",
                "Access-Control-Allow-Headers": "Content-Type,Authorization,X-Requested-With",
                "Access-Control-Allow-Credentials": "true",
                "Vary": "Origin",
                "Access-Control-Max-Age": "86400",
            }
            # 204로 즉시 종료 (200이어도 무방하지만 204 선호)
            return Response(status_code=204, headers=headers)
        return await call_next(request)

app = FastAPI()

app.add_middleware(PreflightMiddleware)
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

@app.options("/{full_path:path}")
def options_any(full_path: str):
    return Response(status_code=204)

# API 라우터 포함
app.include_router(available_router)

# 커스텀 예외 핸들러는 라우터 포함 이후에 추가
app.add_exception_handler(BaseCustomException, custom_exception_handler)
app.add_exception_handler(Exception, global_exception_handler)

# 로깅 설정(콘솔 + 일자별 파일 로테이션, JSON 포맷)
setup_logging()
