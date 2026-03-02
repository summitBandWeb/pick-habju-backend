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
async def test_fetch_business_query_contains_extended_fields():
    fetcher = NaverRoomFetcher()
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

    payload = mock_client.post.await_args.kwargs["json"]
    query = payload["query"]

    required_fields = [
        "desc",
        "addressJson",
        "phoneInformationJson",
        "placeScheduleJson",
        "extraDescJson",
        "additionalPropertyJson",
        "eventDescJson",
    ]
    for field in required_fields:
        assert field in query


@pytest.mark.asyncio
async def test_fetch_biz_items_query_contains_extended_fields():
    fetcher = NaverRoomFetcher()
    mock_client = AsyncMock()
    mock_client.post.return_value = _DummyResponse({"data": {"bizItems": []}})

    await fetcher._fetch_biz_items(mock_client, "522011")

    payload = mock_client.post.await_args.kwargs["json"]
    query = payload["query"]

    required_fields = [
        "stock",
        "minBookingCount",
        "maxBookingCount",
        "minBookingTime",
        "maxBookingTime",
        "isOnsitePayment",
        "bookingCountSettingJson",
        "extraFeeSettingJson",
        "extraDescJson",
    ]
    for field in required_fields:
        assert field in query
