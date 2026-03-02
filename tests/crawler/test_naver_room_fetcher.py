import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

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


@pytest.mark.asyncio
async def test_fetch_full_info_uses_business_fallback_when_business_is_null():
    fetcher = NaverRoomFetcher()

    with patch.object(fetcher, "_fetch_business", AsyncMock(return_value=None)), patch.object(
        fetcher,
        "_fetch_biz_items",
        AsyncMock(return_value=[{"bizItemId": "3968885", "name": "블랙룸", "desc": "desc"}]),
    ), patch.object(fetcher, "_fetch_near_subway", AsyncMock(return_value=None)):
        result = await fetcher.fetch_full_info("522011")

    assert result is not None
    assert result["business"]["businessId"] == "522011"
    assert result["business"]["businessDisplayName"] == "블랙룸"
    assert len(result["rooms"]) == 1


@pytest.mark.asyncio
async def test_post_graphql_retries_on_rate_limit():
    fetcher = NaverRoomFetcher()
    fetcher.RATE_LIMIT_RETRIES = 2
    fetcher.RATE_LIMIT_BACKOFF_SEC = 0.0
    fetcher.RATE_LIMIT_JITTER_SEC = 0.0

    rate_limited = _DummyResponse({"data": {}}, status_code=429)
    ok = _DummyResponse({"data": {"bizItems": []}}, status_code=200)

    mock_client = AsyncMock()
    mock_client.post.side_effect = [rate_limited, ok]

    with patch("app.crawler.naver_room_fetcher.asyncio.sleep", new=AsyncMock()) as sleep_mock:
        response = await fetcher._post_graphql(
            mock_client,
            payload={"operationName": "bizItems"},
            operation_name="bizItems",
        )

    assert response.status_code == 200
    assert mock_client.post.await_count == 2
    sleep_mock.assert_awaited_once()


@pytest.mark.asyncio
async def test_post_graphql_returns_last_429_when_retries_exhausted():
    fetcher = NaverRoomFetcher()
    fetcher.RATE_LIMIT_RETRIES = 1
    fetcher.RATE_LIMIT_BACKOFF_SEC = 0.0
    fetcher.RATE_LIMIT_JITTER_SEC = 0.0

    rate_limited = _DummyResponse({"data": {}}, status_code=429)

    mock_client = AsyncMock()
    mock_client.post.side_effect = [rate_limited, rate_limited]

    with patch("app.crawler.naver_room_fetcher.asyncio.sleep", new=AsyncMock()) as sleep_mock:
        response = await fetcher._post_graphql(
            mock_client,
            payload={"operationName": "business"},
            operation_name="business",
        )

    assert response.status_code == 429
    assert mock_client.post.await_count == 2
    sleep_mock.assert_awaited_once()


def test_fetcher_loads_cookie_header_from_storage_state(tmp_path: Path):
    state = {
        "cookies": [
            {"name": "NID_SES", "value": "abc", "domain": ".naver.com"},
            {"name": "NID_AUT", "value": "def", "domain": "booking.naver.com"},
            {"name": "OTHER", "value": "zzz", "domain": "example.com"},
        ]
    }
    state_path = tmp_path / "state.json"
    state_path.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")

    with patch.dict("os.environ", {"NAVER_STORAGE_STATE_PATH": str(state_path)}, clear=False):
        fetcher = NaverRoomFetcher()

    assert "Cookie" in fetcher.headers
    assert "NID_SES=abc" in fetcher.headers["Cookie"]
    assert "NID_AUT=def" in fetcher.headers["Cookie"]
    assert "OTHER=zzz" not in fetcher.headers["Cookie"]


def test_fetcher_prefers_cookie_header_env_over_storage_state(tmp_path: Path):
    state = {"cookies": [{"name": "NID_SES", "value": "abc", "domain": ".naver.com"}]}
    state_path = tmp_path / "state.json"
    state_path.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")

    with patch.dict(
        "os.environ",
        {
            "NAVER_STORAGE_STATE_PATH": str(state_path),
            "NAVER_COOKIE_HEADER": "NID_SES=manual",
        },
        clear=False,
    ):
        fetcher = NaverRoomFetcher()

    assert fetcher.headers.get("Cookie") == "NID_SES=manual"
