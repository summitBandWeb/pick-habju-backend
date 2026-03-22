import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from datetime import datetime, timedelta
from app.models.dto import RoomDetail


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
