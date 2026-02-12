# =============================================================================
# Cloud Run 최적화 미들웨어
# =============================================================================
# - Cache-Control: API 응답 캐시 방지
# - Real IP: Cloudflare 프록시 뒤 실제 클라이언트 IP 추출
# =============================================================================

import logging
import uuid
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response
from app.core.context import set_trace_id

logger = logging.getLogger(__name__)


class TraceIDMiddleware(BaseHTTPMiddleware):
    """
    모든 요청에 대해 고유한 Trace ID를 관리합니다.
    클라이언트가 X-Trace-ID 헤더를 보내면 이를 사용하고, 없으면 신규 UUID를 생성(Fallback)합니다.
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        # 1. 클라이언트가 보낸 Trace ID 확인 (우선순위 높음)
        trace_id = request.headers.get("X-Trace-ID")
        
        # 2. 없으면 신규 생성 (Fallback for Swagger, Postman, internal calls)
        if not trace_id:
            trace_id = str(uuid.uuid4())
        
        # 3. 컨텍스트 변수에 설정 (로거에서 참조 가능)
        set_trace_id(trace_id)
        request.state.trace_id = trace_id
        
        response = await call_next(request)
        
        # 4. 응답 헤더에 Trace ID 포함
        response.headers["X-Trace-ID"] = trace_id
        return response


class CacheControlMiddleware(BaseHTTPMiddleware):
    """
    API 경로에 대해 Cache-Control 헤더를 추가하여 캐싱을 방지합니다.
    Cloudflare의 Cache Bypass 규칙과 함께 이중 보호를 제공합니다.
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        response = await call_next(request)

        # /api 경로에 대해서만 캐시 방지 헤더 추가
        if request.url.path.startswith("/api"):
            response.headers["Cache-Control"] = (
                "no-store, no-cache, must-revalidate, max-age=0"
            )
            response.headers["Pragma"] = "no-cache"
            response.headers["Expires"] = "0"

        return response


class RealIPMiddleware(BaseHTTPMiddleware):
    """
    Cloudflare 프록시 뒤에서 실제 클라이언트 IP를 추출하여 로깅합니다.

    IP 추출 우선순위:
    1. CF-Connecting-IP (Cloudflare 전용)
    2. X-Forwarded-For의 첫 번째 IP
    3. X-Real-IP
    4. request.client.host (폴백)
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        # 실제 클라이언트 IP 추출
        real_ip = self._get_real_ip(request)

        # request.state에 저장하여 다른 곳에서 사용 가능
        request.state.real_ip = real_ip

        # 로깅 (헬스체크 제외)
        if request.url.path != "/ping":
            logger.info(
                f"[{real_ip}] {request.method} {request.url.path}",
                extra={
                    "real_ip": real_ip,
                    "method": request.method,
                    "path": request.url.path,
                    "user_agent": request.headers.get("User-Agent", ""),
                    "referer": request.headers.get("Referer", ""),
                    "request_id": request.headers.get("X-Request-ID", ""),
                },
            )

        response = await call_next(request)
        return response

    def _get_real_ip(self, request: Request) -> str:
        """Cloudflare 및 프록시 헤더에서 실제 IP 추출"""

        # 1. Cloudflare의 실제 클라이언트 IP (가장 신뢰)
        cf_connecting_ip = request.headers.get("CF-Connecting-IP")
        if cf_connecting_ip:
            return cf_connecting_ip.strip()

        # 2. X-Forwarded-For (첫 번째 IP가 원래 클라이언트)
        x_forwarded_for = request.headers.get("X-Forwarded-For")
        if x_forwarded_for:
            # 여러 프록시를 거친 경우 쉼표로 구분됨
            return x_forwarded_for.split(",")[0].strip()

        # 3. X-Real-IP (일부 프록시에서 사용)
        x_real_ip = request.headers.get("X-Real-IP")
        if x_real_ip:
            return x_real_ip.strip()

        # 4. 폴백: 직접 연결된 클라이언트 IP
        if request.client:
            return request.client.host

        return "unknown"


def get_real_ip(request: Request) -> str:
    """
    request.state에서 실제 IP를 가져오는 헬퍼 함수.
    RealIPMiddleware가 적용된 후에만 사용 가능.
    """
    return getattr(request.state, "real_ip", "unknown")
