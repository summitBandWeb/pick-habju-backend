import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from datetime import datetime
from app.services.availability_service import AvailabilityService
from app.models.dto import AvailabilityRequest, RoomAvailability, RoomDetail, PolicyWarning


@pytest.fixture
def mock_pricing_service():
    return MagicMock()


@pytest.fixture
def service(mock_pricing_service):
    # 크롤러는 테스트하지 않으므로 빈 맵 주입
    svc = AvailabilityService({})
    svc.pricing_service = mock_pricing_service
    return svc


class TestApplyPolicies:

    def test_1hour_reservation_warning(self, service):
        """1시간 예약인데 canReserveOneHour=False면 경고 발생"""
        req = AvailabilityRequest(
            date="2024-01-01", capacity=2, start_hour="14:00", end_hour="15:00",
            swLat=0, swLng=0, neLat=0, neLng=0
        )
        slots = ["14:00"]

        room = RoomDetail(
            name="TestRoom", branch="Branch", business_id="b1", biz_item_id="r1",
            pricePerHour=10000, can_reserve_one_hour=False, requires_call_on_sameday=False,
            max_capacity=10, recommend_capacity=5
        )
        avail = RoomAvailability(room_detail=room, available=True, available_slots={"14:00": True})

        results = service._apply_policies([avail], req, slots)

        assert len(results) == 1
        assert len(results[0].policy_warnings) == 1
        assert results[0].policy_warnings[0].type == "call_required_1h"

    def test_sameday_reservation_warning(self, service):
        """당일 예약인데 requiresCallOnSameDay=True면 경고 발생"""
        today = datetime.now().strftime("%Y-%m-%d")
        req = AvailabilityRequest(
            date=today, capacity=2, start_hour="14:00", end_hour="16:00",
            swLat=0, swLng=0, neLat=0, neLng=0
        )
        slots = ["14:00", "15:00"]

        room = RoomDetail(
            name="TestRoom", branch="Branch", business_id="b1", biz_item_id="r1",
            pricePerHour=10000, can_reserve_one_hour=True, requires_call_on_sameday=True,
            max_capacity=10, recommend_capacity=5
        )
        avail = RoomAvailability(room_detail=room, available=True, available_slots={})

        results = service._apply_policies([avail], req, slots)

        assert len(results[0].policy_warnings) == 1
        assert results[0].policy_warnings[0].type == "call_required_today"

    def test_price_calculation_integration(self, service, mock_pricing_service):
        """PricingService가 호출되어 estimated_price가 설정되는지 검증"""
        req = AvailabilityRequest(
            date="2024-01-01", capacity=4, start_hour="14:00", end_hour="16:00",
            swLat=0, swLng=0, neLat=0, neLng=0
        )
        slots = ["14:00", "15:00"]

        room = RoomDetail(
            name="TestRoom", branch="Branch", business_id="b1", biz_item_id="r1",
            pricePerHour=10000, max_capacity=10, recommend_capacity=5,
            price_config=[], base_capacity=4, extra_charge=5000,
            can_reserve_one_hour=True, requires_call_on_sameday=False
        )
        avail = RoomAvailability(room_detail=room, available=True, available_slots={})

        mock_pricing_service.calculate_total_price.return_value = 30000

        results = service._apply_policies([avail], req, slots)

        mock_pricing_service.calculate_total_price.assert_called_once()
        assert results[0].estimated_price == 30000

    def test_price_calculation_error_handling(self, service, mock_pricing_service):
        """가격 계산 중 에러 발생 시 estimated_price는 None"""
        req = AvailabilityRequest(
            date="2024-01-01", capacity=4, start_hour="14:00", end_hour="16:00",
            swLat=0, swLng=0, neLat=0, neLng=0
        )
        slots = ["14:00", "15:00"]

        room = RoomDetail(
            name="TestRoom", branch="Branch", business_id="b1", biz_item_id="r1",
            pricePerHour=10000, max_capacity=10, recommend_capacity=5,
            can_reserve_one_hour=True, requires_call_on_sameday=False
        )
        avail = RoomAvailability(room_detail=room, available=True, available_slots={})

        mock_pricing_service.calculate_total_price.side_effect = ValueError("Calc Failed")

        results = service._apply_policies([avail], req, slots)

        assert results[0].estimated_price is None


class TestCheckAvailabilityFlow:
    """check_availability 전체 흐름 테스트 (DB/Crawler Mocking)

    Rationale:
        DB에 실제 데이터가 없어도 `get_rooms_by_criteria`와 크롤러를 Mock하여
        서비스 로직 전체를 검증할 수 있음. 외부 의존성 없이 비즈니스 로직만 격리 테스트.
    """

    @pytest.fixture
    def mock_crawler(self):
        crawler = MagicMock()
        crawler.check_availability = AsyncMock()
        return crawler

    @pytest.fixture
    def service(self, mock_crawler, mock_pricing_service):
        svc = AvailabilityService({"mock_crawler": mock_crawler})
        svc.pricing_service = mock_pricing_service
        return svc

    @pytest.mark.asyncio
    async def test_full_flow_with_mock_data(self, service, mock_crawler, mock_pricing_service):
        """DB 데이터가 없어도 Mock으로 전체 흐름 검증"""
        # Given
        req = AvailabilityRequest(
            date="2026-02-14", capacity=3, start_hour="14:00", end_hour="16:00",
            swLat=0, swLng=0, neLat=0, neLng=0
        )

        mock_room = RoomDetail(
            name="MockRoom", branch="MockBranch", business_id="b1", biz_item_id="r1",
            pricePerHour=10000, max_capacity=10, recommend_capacity=5,
            can_reserve_one_hour=True, requires_call_on_sameday=False,
            recommend_capacity_range=[4, 8], price_config=[]
        )

        # NOTE: RoomResult = Union[RoomAvailability, Exception] (타입 alias)
        # 크롤러 성공 시 RoomAvailability를 반환하므로 그대로 사용
        mock_crawler_result = RoomAvailability(
            room_detail=mock_room,
            available=True,
            available_slots={"14:00": True, "15:00": True}
        )
        mock_crawler.check_availability.return_value = [mock_crawler_result]

        mock_pricing_service.calculate_total_price.return_value = 20000

        # When
        with patch("app.services.availability_service.get_rooms_by_criteria") as mock_db, \
             patch("app.services.availability_service.validate_map_coordinates"), \
             patch("app.services.availability_service.filter_rooms_by_type", return_value=[mock_room]), \
             patch("app.services.availability_service.validate_availability_request"):
            mock_db.return_value = [mock_room]
            response = await service.check_availability(req)

        # Then
        assert len(response.results) == 1
        res = response.results[0]

        # 1. 크롤러 결과가 잘 들어왔는지
        assert res.room_detail.name == "MockRoom"
        assert res.available is True

        # 2. PricingService가 연동되었는지 (Phase 3 검증)
        assert res.estimated_price == 20000
        mock_pricing_service.calculate_total_price.assert_called()

        # 3. DB Mock이 호출되었는지
        mock_db.assert_called_once()
