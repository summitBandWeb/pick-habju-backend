import httpx
import asyncio
import logging
from threading import Lock
from app.exception.api.client_loader_exception import RequestFailedError

# 전역 클라이언트 변수
_shared_client: httpx.AsyncClient = None
_client_lock = Lock()

def set_global_client():
    """애플리케이션 시작 시 전역 클라이언트 설정"""
    global _shared_client
    with _client_lock:
        if _shared_client is None:
            _shared_client = httpx.AsyncClient(
                timeout=httpx.Timeout(10.0, connect=5.0),
                limits=httpx.Limits(max_keepalive_connections=20, max_connections=100),
                http2=True,
            )

async def close_global_client():
    """애플리케이션 종료 시 전역 클라이언트 리소스 해제"""
    global _shared_client
    with _client_lock:
        if _shared_client:
            await _shared_client.aclose()
            _shared_client = None

async def get_client() -> httpx.AsyncClient:
    """전역 클라이언트 반환 (없으면 생성 - 안전장치)"""
    if _shared_client is None:
        return httpx.AsyncClient()
    return _shared_client

async def load_client(url: str, **kwargs):
    logger = logging.getLogger("app")
    
    # 1. 사용할 클라이언트 결정 (전역 vs 임시)
    client = _shared_client
    should_close = False
    
    if client is None:
        # 안전장치: 전역 클라이언트가 설정되지 않았다면 임시로 생성
        client = httpx.AsyncClient(
            timeout=httpx.Timeout(10.0, connect=5.0)
        )
        should_close = True

    try:
        try:
            response = await client.post(url, **kwargs)
            response.raise_for_status()
            return response
        except httpx.HTTPStatusError as e:
            status = e.response.status_code if e.response is not None else None
            # 5xx는 일시 장애 가능성 → 짧게 재시도
            if status is not None and status >= 500:
                for attempt in range(2):
                    try:
                        await asyncio.sleep(0.2 * (attempt + 1))
                        response = await client.post(url, **kwargs)
                        response.raise_for_status()
                        return response
                    except Exception:
                        continue
            logger.error({
                "timestamp": None,
                "status": e.response.status_code if e.response else 500,
                "errorCode": "API-001",
                "message": "외부 API 호출에 실패했습니다.",
            })
            raise RequestFailedError("외부 API 호출에 실패했습니다.")
        except (httpx.ConnectError, httpx.ReadTimeout, httpx.WriteError, httpx.NetworkError) as e:
            # 네트워크/타임아웃류는 단기 재시도
            for attempt in range(2):
                try:
                    await asyncio.sleep(0.2 * (attempt + 1))
                    response = await client.post(url, **kwargs)
                    response.raise_for_status()
                    return response
                except Exception:
                    continue
            logger.error({
                "timestamp": None,
                "status": 503,
                "errorCode": "API-001",
                "message": "외부 API 호출에 실패했습니다.",
            })
            raise RequestFailedError("외부 API 호출에 실패했습니다.")
        except Exception:
            logger.error({
                "timestamp": None,
                "status": 503,
                "errorCode": "API-001",
                "message": "외부 API 호출에 실패했습니다.",
            })
            raise RequestFailedError("외부 API 호출에 실패했습니다.")
            
    finally:
        # 2. 임시로 생성했던 클라이언트라면 닫아주기 (전역은 닫으면 안 됨!)
        if should_close:
            await client.aclose()
