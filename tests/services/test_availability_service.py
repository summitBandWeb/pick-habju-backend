import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from datetime import datetime, timedelta
from app.services.availability_service import AvailabilityService
from app.models.dto import AvailabilityRequest, RoomAvailability, RoomDetail


# 미래 날짜를 사용하여 DTO 날짜 검증을 통과시킴
FUTURE_DATE = (datetime.now() + timedelta(days=30)).strftime("%Y-%m-%d")


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
            date=FUTURE_DATE, capacity=2, start_hour="14:00", end_hour="15:00",
            swLat=37.0, swLng=126.0, neLat=38.0, neLng=127.0
        )
        # NOTE: generate_time_slots("14:00", "15:00") → ["14:00", "15:00"] (end-inclusive)
        #        len(slots) - 1 == 1 → 1시간 예약으로 감지
        slots = ["14:00", "15:00"]

        room = RoomDetail(
            name="TestRoom", branch="Branch", business_id="b1", biz_item_id="r1",
            pricePerHour=10000, can_reserve_one_hour=False, requiresContactOnSameDay=False,
            max_capacity=10, recommend_capacity_range=[3, 5],
            # NOTE: 이슈 2-1 필터링 조건 통과를 위해 phoneNumber 필수
            phoneNumber="010-1234-5678"
        )
        avail = RoomAvailability(room_detail=room, available=True, available_slots={"14:00": True})

        results = service._apply_policies([avail], req, slots)

        assert len(results) == 1
        assert len(results[0].policy_warnings) == 1
        assert results[0].policy_warnings[0].type == "call_required_1h"

    def test_1h_reservation_chat_required(self, service):
        """1시간 예약 불가 방(전화번호 없음, displayName 있음) → 채팅 문의 경고 추가"""
        req = AvailabilityRequest(
            date=FUTURE_DATE, capacity=2, start_hour="14:00", end_hour="15:00",
            swLat=37.0, swLng=126.0, neLat=38.0, neLng=127.0
        )
        slots = ["14:00", "15:00"]
        room = RoomDetail(
            name="TestRoom", branch="Branch", business_id="b1", biz_item_id="r1",
            pricePerHour=10000, can_reserve_one_hour=False, requiresContactOnSameDay=False,
            max_capacity=10, recommend_capacity_range=[3, 5],
            phoneNumber=None, displayName="테스트 톡톡"
        )
        avail = RoomAvailability(room_detail=room, available=True, available_slots={"14:00": True})
        results = service._apply_policies([avail], req, slots)

        assert len(results) == 1
        assert len(results[0].policy_warnings) == 1
        assert results[0].policy_warnings[0].type == "chat_required_1h"

    def test_1h_reservation_excluded_no_contact(self, service):
        """1시간 예약 불가 방 + 연락수단 모두 없음 → 검색 대상에서 제외됨"""
        req = AvailabilityRequest(
            date=FUTURE_DATE, capacity=2, start_hour="14:00", end_hour="15:00",
            swLat=37.0, swLng=126.0, neLat=38.0, neLng=127.0
        )
        slots = ["14:00", "15:00"]
        room = RoomDetail(
            name="TestRoom", branch="Branch", business_id="b1", biz_item_id="r1",
            pricePerHour=10000, can_reserve_one_hour=False, requiresContactOnSameDay=False,
            max_capacity=10, recommend_capacity_range=[3, 5],
            phoneNumber=None, displayName=None
        )
        avail = RoomAvailability(room_detail=room, available=True, available_slots={"14:00": True})
        results = service._apply_policies([avail], req, slots)

        assert len(results) == 0

    def test_sameday_reservation_warning(self, service):
        """당일 예약인데 requiresCallOnSameDay=True면 경고 발생"""
        # 테스트 시점에 따라 과거 시간 유효성 검사 실패가 발생하지 않도록 시간을 명시적으로 고정
        now = datetime.now().replace(hour=12, minute=0, second=0, microsecond=0)
        date = now.strftime("%Y-%m-%d")
        
        # model_construct를 통해 DTO의 과거 시간 밸리데이션(예: 12:00이 현재보다 과거인지)을 바이패스
        req = AvailabilityRequest.model_construct(
            date=date, capacity=2, start_hour="12:00", end_hour="13:00",
            swLat=37.0, swLng=126.0, neLat=38.0, neLng=127.0
        )
        slots = ["12:00", "13:00"]

        room = RoomDetail(
            name="TestRoom", branch="Branch", business_id="b1", biz_item_id="r1",
            pricePerHour=10000, can_reserve_one_hour=True, requiresContactOnSameDay=True,
            max_capacity=10, recommend_capacity_range=[3, 5],
            # NOTE: 이슈 2-1 필터링 조건 통과를 위해 phoneNumber 필수
            phoneNumber="010-1234-5678"
        )
        avail = RoomAvailability(room_detail=room, available=True, available_slots={})

        results = service._apply_policies([avail], req, slots)

        assert len(results[0].policy_warnings) == 1
        assert results[0].policy_warnings[0].type == "call_required_today"

    def test_price_calculation_integration(self, service, mock_pricing_service):
        """PricingService가 호출되어 estimated_price가 설정되는지 검증"""
        req = AvailabilityRequest(
            date=FUTURE_DATE, capacity=4, start_hour="14:00", end_hour="16:00",
            swLat=37.0, swLng=126.0, neLat=38.0, neLng=127.0
        )
        slots = ["14:00", "15:00"]

        room = RoomDetail(
            name="TestRoom", branch="Branch", business_id="b1", biz_item_id="r1",
            pricePerHour=10000, max_capacity=10, recommend_capacity_range=[3, 5],
            price_config=[{"price": 10000}], base_capacity=4, extra_charge=5000,
            can_reserve_one_hour=True, requiresContactOnSameDay=False
        )
        avail = RoomAvailability(room_detail=room, available=True, available_slots={})

        mock_pricing_service.calculate_total_price.return_value = 30000

        results = service._apply_policies([avail], req, slots)

        mock_pricing_service.calculate_total_price.assert_called_once()
        assert results[0].estimated_price == 30000

    def test_price_calculation_error_handling(self, service, mock_pricing_service):
        """가격 계산 중 에러 발생 시 estimated_price는 None"""
        req = AvailabilityRequest(
            date=FUTURE_DATE, capacity=4, start_hour="14:00", end_hour="16:00",
            swLat=37.0, swLng=126.0, neLat=38.0, neLng=127.0
        )
        slots = ["14:00", "15:00"]

        room = RoomDetail(
            name="TestRoom", branch="Branch", business_id="b1", biz_item_id="r1",
            pricePerHour=10000, max_capacity=10, recommend_capacity_range=[3, 5],
            price_config=[{"price": 10000}],
            can_reserve_one_hour=True, requiresContactOnSameDay=False
        )
        avail = RoomAvailability(room_detail=room, available=True, available_slots={})

        mock_pricing_service.calculate_total_price.side_effect = ValueError("Calc Failed")

        results = service._apply_policies([avail], req, slots)

        assert results[0].estimated_price is None

    def test_price_calculation_list_config_supports_24h_end(self, service, mock_pricing_service):
        """list price_config 경로에서 00:00 종료 시각을 다음날 00:00으로 변환"""
        req = AvailabilityRequest(
            date="2099-01-01", capacity=4, start_hour="22:00", end_hour="00:00",
            swLat=0.0, swLng=0.0, neLat=1.0, neLng=1.0
        )
        slots = ["22:00", "23:00", "00:00"]

        room = RoomDetail(
            name="TestRoom", branch="Branch", business_id="b1", biz_item_id="r1",
            pricePerHour=10000, max_capacity=10, recommend_capacity_range=[3, 5],
            price_config=[{"price": 10000}],
            can_reserve_one_hour=True, requiresContactOnSameDay=False
        )
        avail = RoomAvailability(room_detail=room, available=True, available_slots={})

        mock_pricing_service.calculate_total_price.return_value = 20000

        results = service._apply_policies([avail], req, slots)

        kwargs = mock_pricing_service.calculate_total_price.call_args.kwargs
        assert kwargs["start_dt"] == datetime(2099, 1, 1, 22, 0)
        assert kwargs["end_dt"] == datetime(2099, 1, 2, 0, 0)
        assert results[0].estimated_price == 20000


class TestAvailabilityServiceFlow:
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
            date=FUTURE_DATE, capacity=3, start_hour="14:00", end_hour="16:00",
            swLat=37.0, swLng=126.0, neLat=38.0, neLng=127.0
        )

        mock_room = RoomDetail(
            name="MockRoom", branch="MockBranch", business_id="b1", biz_item_id="r1",
            pricePerHour=10000, max_capacity=10,
            can_reserve_one_hour=True, requiresContactOnSameDay=False,
            recommend_capacity_range=[4, 8], price_config=[{"price": 10000}]
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
             patch("app.services.availability_service.filter_rooms_by_type", return_value=[mock_room]), \
             patch("app.services.availability_service.validate_availability_request"):
            mock_db.return_value = [mock_room]
            response = await service.check_availability(req)

        # Then
        assert len(response.branches) == 1
        branch = response.branches[0]
        assert len(branch.rooms) == 1
        res = branch.rooms[0]

        # 1. 크롤러 결과가 잘 들어왔는지
        assert res.name == "MockRoom"
        assert res.available is True

        # 2. PricingService가 연동되었는지 (Phase 3 검증)
        assert res.estimated_price == 20000
        mock_pricing_service.calculate_total_price.assert_called()

        # 3. DB Mock이 호출되었는지
        mock_db.assert_called_once()
