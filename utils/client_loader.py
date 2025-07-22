import httpx
from exception.utils.client_loader_exception import RequestFailedError

async def load_client(url: str, **kwargs):
  async with httpx.AsyncClient() as client:
    try:
      response = await client.post(url, **kwargs)
      response.raise_for_status()
      return response
    except Exception as e:
      raise RequestFailedError(f"API 응답 요청 실패 오류: {e}")