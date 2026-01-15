import httpx
import asyncio
import logging
from datetime import datetime
from app.exception.api.client_loader_exception import RequestFailedError

# 전역 클라이언트 변수
_shared_client: httpx.AsyncClient = None
_client_lock = asyncio.Lock()

async def set_global_client():
    """애플리케이션 시작 시 전역 클라이언트 설정.
    
    비동기 Lock을 사용하여 여러 비동기 작업이 동시에 초기화를 시도해도
    단일 인스턴스만 생성되도록 보장합니다.
    
    HTTP/2 지원 및 연결 풀 최적화 설정:
    - Timeout: 전체 10초, 연결 5초
    - 연결 풀: 최대 100개 연결, keepalive 20개
    """
    global _shared_client
    async with _client_lock:
        if _shared_client is None:
            _shared_client = httpx.AsyncClient(
                timeout=httpx.Timeout(10.0, connect=5.0),
                limits=httpx.Limits(max_keepalive_connections=20, max_connections=100),
                http2=True,
            )

async def close_global_client():
    """애플리케이션 종료 시 전역 클라이언트 리소스 해제.
    
    모든 연결을 정상적으로 종료하고 리소스를 정리합니다.
    """
    global _shared_client
    async with _client_lock:
        if _shared_client:
            await _shared_client.aclose()
            _shared_client = None

async def _retry_request(client: httpx.AsyncClient, url: str, max_retries: int = 2, **kwargs):
    """재시도 로직을 분리한 헬퍼 함수.
    
    네트워크 오류나 5xx 서버 에러 발생 시 지수 백오프로 재시도합니다.
    
    Args:
        client: HTTP 클라이언트 인스턴스
        url: 요청 URL
        max_retries: 최대 재시도 횟수
        **kwargs: POST 요청에 전달할 추가 파라미터
        
    Returns:
        성공한 HTTP 응답 객체
        
    Raises:
        Exception: 모든 재시도 실패 시 마지막 예외를 전파
    """
    for attempt in range(max_retries):
        try:
            # 지수 백오프: 0.2초, 0.4초, 0.6초...
            await asyncio.sleep(0.2 * (attempt + 1))
            response = await client.post(url, **kwargs)
            response.raise_for_status()
            return response
        except Exception:
            if attempt == max_retries - 1:
                raise
            continue
    return None

async def load_client(url: str, **kwargs):
    """외부 API 호출을 위한 HTTP POST 요청 헬퍼.
    
    전역 클라이언트를 사용하여 연결 재사용을 최적화하며,
    네트워크 오류나 5xx 에러 발생 시 자동으로 재시도합니다.
    
    Args:
        url: 요청할 API 엔드포인트 URL
        **kwargs: httpx.AsyncClient.post()에 전달할 추가 파라미터
                 (headers, json, data 등)
    
    Returns:
        httpx.Response: 성공한 HTTP 응답 객체
        
    Raises:
        RequestFailedError: API 호출 실패 시 (4xx, 5xx, 네트워크 오류 등)
        
    Note:
        - 전역 클라이언트가 없으면 임시 클라이언트 생성 (안전장치)
        - 5xx, 네트워크 오류: 자동 재시도 (최대 2회)
        - 4xx: 즉시 실패 (재시도 없음)
    """
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
            # 5xx는 일시 장애 가능성 → 재시도
            if status is not None and status >= 500:
                return await _retry_request(client, url, **kwargs)
            
            # 4xx 등 기타 에러는 즉시 로깅 후 실패
            logger.error({
                "timestamp": datetime.now().isoformat(),
                "status": status if status else 500,
                "errorCode": RequestFailedError.error_code,
                "message": "외부 API 호출에 실패했습니다 (HTTPStatusError).",
                "url": url,
                "error_detail": str(e),
            })
            raise RequestFailedError("외부 API 호출에 실패했습니다.")
            
        except (httpx.ConnectError, httpx.ReadTimeout, httpx.WriteError, httpx.NetworkError) as e:
            # 네트워크/타임아웃류는 재시도
            return await _retry_request(client, url, **kwargs)
            
    except Exception as e:
        # 재시도 실패 또는 기타 예외 발생 시 최종 로깅 (이미 로깅된 4xx 제외)
        if not isinstance(e, RequestFailedError):
            logger.error({
                "timestamp": datetime.now().isoformat(),
                "status": 503,
                "errorCode": RequestFailedError.error_code,
                "message": "외부 API 호출에 실패했습니다.",
                "url": url,
                "error_detail": str(e),
            })
        raise RequestFailedError("외부 API 호출에 실패했습니다.")
            
    finally:
        # 2. 임시로 생성했던 클라이언트라면 닫아주기 (전역은 닫으면 안 됨!)
        if should_close:
            await client.aclose()
