import httpx
import asyncio
import logging
from app.exception.api.client_loader_exception import RequestFailedError


async def load_client(url: str, **kwargs):
  logger = logging.getLogger("app")
  async with httpx.AsyncClient() as client:
    try:
      response = await client.post(url, **kwargs)
      response.raise_for_status()
      return response
    except httpx.HTTPStatusError as e:
      status = e.response.status_code if e.response is not None else None
      # 5xx는 일시 장애 가능성 → 짧게 재시도. 4xx는 즉시 실패
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
    except Exception as e:
      logger.error({
          "timestamp": None,
          "status": 503,
          "errorCode": "API-001",
          "message": "외부 API 호출에 실패했습니다.",
      })
      raise RequestFailedError("외부 API 호출에 실패했습니다.")
