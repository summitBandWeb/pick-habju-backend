from unittest.mock import AsyncMock

import pytest

from app.crawler.naver_room_fetcher import NaverRoomFetcher


class _DummyResponse:
    def __init__(self, data: dict, status_code: int = 200):
        self._data = data
        self.status_code = status_code
        self.text = ""

    def raise_for_status(self):
        return None

    def json(self):
        return self._data


@pytest.mark.asyncio
async def test_fetch_business_uses_request_timeout():
    fetcher = NaverRoomFetcher()
    fetcher.REQUEST_TIMEOUT = 3.5

    mock_client = AsyncMock()
    mock_client.post.return_value = _DummyResponse(
        {
            "data": {
                "business": {
                    "businessId": "522011",
                    "coordinates": [127.0, 37.0],
                }
            }
        }
    )

    await fetcher._fetch_business(mock_client, "522011")

    assert mock_client.post.await_args.kwargs["timeout"] == 3.5


@pytest.mark.asyncio
async def test_fetch_biz_items_uses_request_timeout():
    fetcher = NaverRoomFetcher()
    fetcher.REQUEST_TIMEOUT = 4.2

    mock_client = AsyncMock()
    mock_client.post.return_value = _DummyResponse({"data": {"bizItems": []}})

    await fetcher._fetch_biz_items(mock_client, "522011")

    assert mock_client.post.await_args.kwargs["timeout"] == 4.2


@pytest.mark.asyncio
async def test_fetch_near_subway_uses_request_timeout():
    fetcher = NaverRoomFetcher()
    fetcher.REQUEST_TIMEOUT = 5.7

    mock_client = AsyncMock()
    mock_client.post.return_value = _DummyResponse(
        {"data": {"nearSubway": {"displayName": "홍대입구역"}}}
    )

    await fetcher._fetch_near_subway(mock_client, 37.0, 127.0, "place-id")

    assert mock_client.post.await_args.kwargs["timeout"] == 5.7
