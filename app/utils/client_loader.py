import httpx
import asyncio
import logging
from typing import Iterable
from app.exception.api.client_loader_exception import RequestFailedError


logger = logging.getLogger("app")

async def load_client(
    client: httpx.AsyncClient,
    method: str,
    url: str,
    *,
    retries: int = 2,
    backoff: float = 0.2,
    retry_on_status: Iterable[int] = (500, 502, 503, 504, 429),
    **kwargs,
) -> httpx.Response:
    """
    재사용 AsyncClient로 요청.
    """
    for attempt in range(retries + 1):
      try:
        response = await client.request(method.upper(), url, **kwargs)
        # 일시 장애 가능성 있는 status는 짧게 재시도
        if response.status_code in retry_on_status and attempt < retries:
                await asyncio.sleep(backoff * (attempt + 1))
                continue
        response.raise_for_status()
        return response
      except httpx.HTTPStatusError as e:
        status = e.response.status_code if e.response is not None else None
        if status in retry_on_status and attempt < retries:
                await asyncio.sleep(backoff * (attempt + 1))
                continue
        logger.error({
            "timestamp": None,
            "status": status if e.response else 500,
            "errorCode": "API-001",
            "message": "외부 API 호출에 실패했습니다.",
        })
        raise RequestFailedError("외부 API 호출에 실패했습니다.")
      except (httpx.ConnectError, httpx.ReadTimeout, httpx.WriteError, httpx.NetworkError) as e:
        # 네트워크/타임아웃류는 단기 재시도
        if attempt < retries:
            await asyncio.sleep(backoff * (attempt + 1))
            continue
        logger.error({
            "timestamp": None,
            "status": 503,
            "errorCode": "API-001",
            "message": "외부 API 호출에 실패했습니다.",
        })
        raise RequestFailedError("외부 API 호출에 실패했습니다.")
      except Exception as e:
        logger.error({
            "timestamp": None,
            "status": 503,
            "errorCode": "API-001",
            "message": "외부 API 호출에 실패했습니다.",
        })
        raise RequestFailedError("외부 API 호출에 실패했습니다.")
