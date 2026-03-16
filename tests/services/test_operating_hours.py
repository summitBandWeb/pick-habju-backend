import pytest
from unittest.mock import MagicMock
from datetime import datetime, timedelta
from app.services.availability_service import AvailabilityService
from app.models.dto import RoomDetail, RoomAvailability


FUTURE_DATE = (datetime.now() + timedelta(days=30)).strftime("%Y-%m-%d")


@pytest.fixture
def service():
    svc = AvailabilityService({})
    svc.pricing_service = MagicMock()
    return svc


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


def _make_result(room, available_slots):
    available = all(available_slots.values()) if available_slots else False
    return RoomAvailability(
        room_detail=room,
        available=available,
        available_slots=available_slots,
    )


class TestOperatingHoursProperty:

    def test_returns_operating_hours_from_price_config(self):
        room = _make_room({"default": 10000, "operating_hours": {"start": "09:00", "end": "23:00"}})
        assert room.operatingHours == {"start": "09:00", "end": "23:00"}

    def test_returns_none_when_not_set(self):
        room = _make_room({"default": 10000})
        assert room.operatingHours is None

    def test_returns_none_for_empty_price_config(self):
        room = _make_room({})
        assert room.operatingHours is None

    def test_returns_none_for_list_price_config(self):
        room = _make_room()
        room.priceConfig = [{"price": 10000}]
        assert room.operatingHours is None

    def test_returns_none_for_malformed_operating_hours(self):
        room = _make_room({"operating_hours": {"start": "09:00"}})
        assert room.operatingHours is None


class TestIsWithinOperatingHours:

    def test_normal_hours_inside(self):
        oh = {"start": "09:00", "end": "23:00"}
        assert AvailabilityService._is_within_operating_hours("09:00", oh) is True
        assert AvailabilityService._is_within_operating_hours("14:00", oh) is True
        assert AvailabilityService._is_within_operating_hours("22:00", oh) is True

    def test_normal_hours_outside(self):
        oh = {"start": "09:00", "end": "23:00"}
        assert AvailabilityService._is_within_operating_hours("08:00", oh) is False
        assert AvailabilityService._is_within_operating_hours("23:00", oh) is False
        assert AvailabilityService._is_within_operating_hours("00:00", oh) is False

    def test_overnight_hours_inside(self):
        oh = {"start": "22:00", "end": "06:00"}
        assert AvailabilityService._is_within_operating_hours("22:00", oh) is True
        assert AvailabilityService._is_within_operating_hours("23:00", oh) is True
        assert AvailabilityService._is_within_operating_hours("00:00", oh) is True
        assert AvailabilityService._is_within_operating_hours("05:00", oh) is True

    def test_overnight_hours_outside(self):
        oh = {"start": "22:00", "end": "06:00"}
        assert AvailabilityService._is_within_operating_hours("06:00", oh) is False
        assert AvailabilityService._is_within_operating_hours("14:00", oh) is False
        assert AvailabilityService._is_within_operating_hours("21:00", oh) is False

    def test_24h_operation(self):
        oh = {"start": "00:00", "end": "24:00"}
        assert AvailabilityService._is_within_operating_hours("00:00", oh) is True
        assert AvailabilityService._is_within_operating_hours("12:00", oh) is True
        assert AvailabilityService._is_within_operating_hours("23:00", oh) is True


class TestFilterByOperatingHours:

    def test_filters_slots_outside_normal_hours(self, service):
        room = _make_room({"operating_hours": {"start": "09:00", "end": "23:00"}})
        res = _make_result(room, {
            "08:00": True, "09:00": True, "14:00": True, "22:00": True, "23:00": True,
        })
        service._filter_by_operating_hours(res)

        assert res.available_slots["08:00"] is False  # 영업 전
        assert res.available_slots["09:00"] is True   # 영업 시작
        assert res.available_slots["14:00"] is True   # 영업 중
        assert res.available_slots["22:00"] is True   # 영업 중
        assert res.available_slots["23:00"] is False  # 영업 종료
        assert res.available is False  # 일부 False이므로

    def test_filters_slots_outside_overnight_hours(self, service):
        room = _make_room({"operating_hours": {"start": "22:00", "end": "06:00"}})
        res = _make_result(room, {
            "21:00": True, "22:00": True, "23:00": True,
            "00:00": True, "05:00": True, "06:00": True,
        })
        service._filter_by_operating_hours(res)

        assert res.available_slots["21:00"] is False  # 영업 전
        assert res.available_slots["22:00"] is True
        assert res.available_slots["23:00"] is True
        assert res.available_slots["00:00"] is True
        assert res.available_slots["05:00"] is True
        assert res.available_slots["06:00"] is False  # 영업 종료

    def test_no_filtering_when_operating_hours_not_set(self, service):
        room = _make_room({"default": 10000})
        res = _make_result(room, {"03:00": True, "04:00": True})
        service._filter_by_operating_hours(res)

        assert res.available_slots["03:00"] is True
        assert res.available_slots["04:00"] is True
        assert res.available is True

    def test_available_recalculated_to_true_when_all_in_range(self, service):
        room = _make_room({"operating_hours": {"start": "09:00", "end": "23:00"}})
        res = _make_result(room, {"10:00": True, "11:00": True, "12:00": True})
        service._filter_by_operating_hours(res)

        assert res.available is True

    def test_already_false_slots_stay_false(self, service):
        room = _make_room({"operating_hours": {"start": "09:00", "end": "23:00"}})
        res = _make_result(room, {"10:00": False, "11:00": True})
        service._filter_by_operating_hours(res)

        assert res.available_slots["10:00"] is False  # 원래 False, 그대로
        assert res.available_slots["11:00"] is True
        assert res.available is False


class TestFetchRoomOperatingHours:

    @pytest.mark.asyncio
    async def test_extracts_operating_hours_from_isUnitBusinessDay(self):
        """isUnitBusinessDay=True인 슬롯 범위로 영업시간을 추출한다."""
        from app.crawler.naver_room_fetcher import NaverRoomFetcher
        from unittest.mock import AsyncMock, patch

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
        """전 시간대가 영업이면 제한 없음(None)을 반환한다."""
        from app.crawler.naver_room_fetcher import NaverRoomFetcher
        from unittest.mock import AsyncMock, patch

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
        """isUnitBusinessDay=True인 슬롯이 없으면 None을 반환한다."""
        from app.crawler.naver_room_fetcher import NaverRoomFetcher
        from unittest.mock import AsyncMock, patch

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
        """심야 룸(00:00~06:00)의 영업시간을 올바르게 추출한다."""
        from app.crawler.naver_room_fetcher import NaverRoomFetcher
        from unittest.mock import AsyncMock, patch

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
    async def test_returns_none_on_api_failure(self):
        from app.crawler.naver_room_fetcher import NaverRoomFetcher
        from unittest.mock import AsyncMock, patch

        mock_response = MagicMock()
        mock_response.status_code = 500

        fetcher = NaverRoomFetcher()
        with patch.object(fetcher, "_post_graphql", new_callable=AsyncMock, return_value=mock_response):
            result = await fetcher.fetch_room_operating_hours("b1", "r1", "2026-03-16")

        assert result is None
