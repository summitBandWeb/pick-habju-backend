import httpx

async def load_client(url: str, **kwargs):
  async with httpx.AsyncClient() as client:
    response = await client.post(url, **kwargs)
  return response