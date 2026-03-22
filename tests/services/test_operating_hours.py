import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from datetime import datetime, timedelta
from app.models.dto import RoomDetail, RoomAvailability


FUTURE_DATE = (datetime.now() + timedelta(days=30)).strftime("%Y-%m-%d")


def _make_room(price_config=None):
    return RoomDetail(
        name="TestRoom",
        branch="Branch",
        business_id="b1",
        biz_item_id="r1",
        pricePerHour=10000,
        can_reserve_one_hour=True,
        requiresContactOnSameDay=False,
        max_capacity=10,
        recommend_capacity_range=[3, 5],
        price_config=price_config or {},
    )


class TestFetchRoomOperatingHours:
    """NaverRoomFetcher.fetch_room_operating_hours() 단위 테스트.

    schedule API의 isUnitBusinessDay 필드에서 룸별 영업시간을 추출하는 로직을 검증한다.
    """

    @pytest.mark.asyncio
    async def test_extracts_operating_hours_from_isUnitBusinessDay(self):
        """연속된 영업 슬롯(09~17시)에서 start/end를 올바르게 추출한다."""
        from app.crawler.naver_room_fetcher import NaverRoomFetcher

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "data": {
                "schedule": {
                    "bizItemSchedule": {
                        "hourly": [
                            {"unitStartTime": "2026-03-16T08:00:00", "isUnitBusinessDay": False},
                            {"unitStartTime": "2026-03-16T09:00:00", "isUnitBusinessDay": True},
                            {"unitStartTime": "2026-03-16T10:00:00", "isUnitBusinessDay": True},
                            {"unitStartTime": "2026-03-16T15:00:00", "isUnitBusinessDay": True},
                            {"unitStartTime": "2026-03-16T17:00:00", "isUnitBusinessDay": True},
                            {"unitStartTime": "2026-03-16T18:00:00", "isUnitBusinessDay": False},
                        ]
                    }
                }
            }
        }

        fetcher = NaverRoomFetcher()
        with patch.object(fetcher, "_post_graphql", new_callable=AsyncMock, return_value=mock_response):
            result = await fetcher.fetch_room_operating_hours("b1", "r1", "2026-03-16")

        assert result == {"start": "09:00", "end": "18:00"}

    @pytest.mark.asyncio
    async def test_returns_none_when_all_slots_are_business_day(self):
        """전 시간대가 영업이면 제한 없음(None) — 24시간 영업."""
        from app.crawler.naver_room_fetcher import NaverRoomFetcher

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "data": {
                "schedule": {
                    "bizItemSchedule": {
                        "hourly": [
                            {"unitStartTime": "2026-03-16T09:00:00", "isUnitBusinessDay": True},
                            {"unitStartTime": "2026-03-16T10:00:00", "isUnitBusinessDay": True},
                            {"unitStartTime": "2026-03-16T11:00:00", "isUnitBusinessDay": True},
                        ]
                    }
                }
            }
        }

        fetcher = NaverRoomFetcher()
        with patch.object(fetcher, "_post_graphql", new_callable=AsyncMock, return_value=mock_response):
            result = await fetcher.fetch_room_operating_hours("b1", "r1", "2026-03-16")

        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_when_no_business_day_slots(self):
        """영업 슬롯이 하나도 없으면 None — 해당일 휴무."""
        from app.crawler.naver_room_fetcher import NaverRoomFetcher

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "data": {
                "schedule": {
                    "bizItemSchedule": {
                        "hourly": [
                            {"unitStartTime": "2026-03-16T09:00:00", "isUnitBusinessDay": False},
                            {"unitStartTime": "2026-03-16T10:00:00", "isUnitBusinessDay": False},
                        ]
                    }
                }
            }
        }

        fetcher = NaverRoomFetcher()
        with patch.object(fetcher, "_post_graphql", new_callable=AsyncMock, return_value=mock_response):
            result = await fetcher.fetch_room_operating_hours("b1", "r1", "2026-03-16")

        assert result is None

    @pytest.mark.asyncio
    async def test_overnight_operating_hours(self):
        """자정 이전 시작 영업(00:00~06:00) — 가장 큰 갭이 07~23시."""
        from app.crawler.naver_room_fetcher import NaverRoomFetcher

        hourly = []
        for h in range(24):
            is_biz = h <= 6  # 00:00~06:00만 True
            hourly.append({
                "unitStartTime": f"2026-03-16T{h:02d}:00:00",
                "isUnitBusinessDay": is_biz,
            })

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "data": {"schedule": {"bizItemSchedule": {"hourly": hourly}}}
        }

        fetcher = NaverRoomFetcher()
        with patch.object(fetcher, "_post_graphql", new_callable=AsyncMock, return_value=mock_response):
            result = await fetcher.fetch_room_operating_hours("b1", "r1", "2026-03-16")

        assert result == {"start": "00:00", "end": "07:00"}

    @pytest.mark.asyncio
    async def test_overnight_wrap_around_operating_hours(self):
        """자정 넘김 영업(22:00~06:00) — 갭 알고리즘으로 wrap-around 처리."""
        from app.crawler.naver_room_fetcher import NaverRoomFetcher

        hourly = []
        for h in range(24):
            # 22:00~23:00 + 00:00~05:00 = True (자정 넘김)
            is_biz = h >= 22 or h <= 5
            hourly.append({
                "unitStartTime": f"2026-03-16T{h:02d}:00:00",
                "isUnitBusinessDay": is_biz,
            })

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "data": {"schedule": {"bizItemSchedule": {"hourly": hourly}}}
        }

        fetcher = NaverRoomFetcher()
        with patch.object(fetcher, "_post_graphql", new_callable=AsyncMock, return_value=mock_response):
            result = await fetcher.fetch_room_operating_hours("b1", "r1", "2026-03-16")

        assert result == {"start": "22:00", "end": "06:00"}

    @pytest.mark.asyncio
    async def test_returns_none_on_api_failure(self):
        """API 500 에러 시 None 반환 (예외 전파 없음)."""
        from app.crawler.naver_room_fetcher import NaverRoomFetcher

        mock_response = MagicMock()
        mock_response.status_code = 500

        fetcher = NaverRoomFetcher()
        with patch.object(fetcher, "_post_graphql", new_callable=AsyncMock, return_value=mock_response):
            result = await fetcher.fetch_room_operating_hours("b1", "r1", "2026-03-16")

        assert result is None


class TestNaverCheckerOperatingHours:
    """NaverCrawler가 isUnitBusinessDay를 반영하여 슬롯 가용성을 판정하는지 검증."""

    @pytest.mark.asyncio
    async def test_non_business_hour_slots_marked_unavailable(self):
        """isUnitBusinessDay=False인 슬롯은 재고와 무관하게 False 처리."""
        from app.crawler.naver_checker import NaverCrawler

        room = _make_room()

        # 09:00 — 재고 있음 + 영업시간 → True
        # 10:00 — 재고 있음 + 비영업 → False
        # 11:00 — 재고 없음 + 영업시간 → False
        mock_api_response = {
            "data": {
                "schedule": {
                    "bizItemSchedule": {
                        "hourly": [
                            {"unitStartTime": "2026-03-16T09:00:00", "unitStock": 1, "unitBookingCount": 0, "isUnitBusinessDay": True},
                            {"unitStartTime": "2026-03-16T10:00:00", "unitStock": 1, "unitBookingCount": 0, "isUnitBusinessDay": False},
                            {"unitStartTime": "2026-03-16T11:00:00", "unitStock": 1, "unitBookingCount": 1, "isUnitBusinessDay": True},
                        ]
                    }
                }
            }
        }

        mock_response = MagicMock()
        mock_response.json.return_value = mock_api_response

        crawler = NaverCrawler()
        with patch("app.crawler.naver_checker.load_client", new_callable=AsyncMock, return_value=mock_response):
            result = await crawler._fetch_naver_availability_room(
                "2026-03-16", ["09:00", "10:00", "11:00"], room,
            )

        assert result.available_slots["09:00"]       # 재고 O + 영업 O
        assert not result.available_slots["10:00"]    # 재고 O + 영업 X
        assert not result.available_slots["11:00"]    # 재고 X + 영업 O

    @pytest.mark.asyncio
    async def test_missing_isUnitBusinessDay_defaults_to_open(self):
        """isUnitBusinessDay 필드가 없으면 영업 중으로 간주 (하위 호환)."""
        from app.crawler.naver_checker import NaverCrawler

        room = _make_room()

        mock_api_response = {
            "data": {
                "schedule": {
                    "bizItemSchedule": {
                        "hourly": [
                            {"unitStartTime": "2026-03-16T09:00:00", "unitStock": 1, "unitBookingCount": 0},
                        ]
                    }
                }
            }
        }

        mock_response = MagicMock()
        mock_response.json.return_value = mock_api_response

        crawler = NaverCrawler()
        with patch("app.crawler.naver_checker.load_client", new_callable=AsyncMock, return_value=mock_response):
            result = await crawler._fetch_naver_availability_room(
                "2026-03-16", ["09:00"], room,
            )

        # isUnitBusinessDay 없어도 기존처럼 재고 기반 판정
        assert result.available_slots["09:00"]
