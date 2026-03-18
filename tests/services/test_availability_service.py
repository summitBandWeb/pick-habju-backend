import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from datetime import datetime, date, timedelta
from app.services.availability_service import AvailabilityService
from app.models.dto import AvailabilityRequest, RoomAvailability, RoomDetail
from app.utils.availability_cache import availability_cache
import unittest.mock as mock


# 미래 날짜를 사용하여 DTO 날짜 검증을 통과시킴
FUTURE_DATE = (datetime.now() + timedelta(days=30)).strftime("%Y-%m-%d")


@pytest.fixture(autouse=True)
def clear_cache():
    availability_cache.clear()
    yield
    availability_cache.clear()

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

    def test_price_calculation_partial_availability(self, service, mock_pricing_service):
        """부분 예약 가능(is_partial)인 경우 estimated_price가 None이 아니라 올바르게 계산되는지 검증"""
        req = AvailabilityRequest(
            date=FUTURE_DATE, capacity=4, start_hour="14:00", end_hour="16:00",
            swLat=37.0, swLng=126.0, neLat=38.0, neLng=127.0
        )
        slots = ["14:00", "15:00", "16:00"]

        room = RoomDetail(
            name="TestRoom", branch="Branch", business_id="b1", biz_item_id="r1",
            pricePerHour=10000, max_capacity=10, recommend_capacity_range=[3, 5],
            price_config=[{"price": 10000}],
            can_reserve_one_hour=True, requiresContactOnSameDay=False
        )
        # available은 False지만, available_slots 중 True가 있으므로 is_partial 상태임
        # NOTE: 16:00은 end-inclusive 슬롯이므로, available_slots에도 포함해야 실제 multi-hour 흐름을 반영함
        avail = RoomAvailability(room_detail=room, available=False, available_slots={"14:00": True, "15:00": False, "16:00": False})

        mock_pricing_service.calculate_total_price.return_value = 10000

        results = service._apply_policies([avail], req, slots)

        assert results[0].estimated_price == 10000

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

    def test_calculate_total_price_partial_longest_block(self, service):
        """가장 긴 연속된 빈 슬롯 블록을 찾아 요금을 계산하는 로직 검증 (min_price_partial)"""
        room = RoomDetail(
            name="TestRoom", branch="Branch", business_id="b1", biz_item_id="r1",
            pricePerHour=10000, max_capacity=10, 
            priceConfig={"default": 10000},
            can_reserve_one_hour=True, requiresContactOnSameDay=False
        )
        
        # hour_slots: 14:00 ~ 18:00 (총 4슬롯 크기, billable_slots = ["14:00", "15:00", "16:00", "17:00"])
        hour_slots = ["14:00", "15:00", "16:00", "17:00", "18:00"]
        
        # available 상태: 14, 15 가능 / 16 불가 / 17 가능
        # 따라서 가장 긴 블록은 ["14:00", "15:00"] (2시간)
        available_slots = {"14:00": True, "15:00": True, "16:00": False, "17:00": True}
        
        # 10000 * 2시간 = 20000원이 연산되어야 함
        # NOTE: 날짜는 요일 무관하므로 far-future 날짜 사용 (과거 만료 방지)
        total_price = service.calculate_total_price(room, "2099-01-06", hour_slots, available_slots)
        assert total_price == 20000

    @pytest.fixture
    def overnight_room(self):
        """평일/주말 day_type 전환 테스트용 공통 RoomDetail.

        priceConfig: weekday 새벽(00~06시) override(15000원) + default(10000원)
        """
        return RoomDetail(
            name="TestRoom", branch="Branch", business_id="b1", biz_item_id="r1",
            pricePerHour=10000, max_capacity=10,
            priceConfig={"default": 10000, "overrides": [{"day_type": "weekday", "start_hour": "00:00", "end_hour": "06:00", "price": 15000}]},
            can_reserve_one_hour=True, requiresContactOnSameDay=False
        )

    def test_calculate_total_price_overnight_weekday(self, service, overnight_room):
        """심야 예약 시 자정을 넘기는 슬롯의 익일 날짜 반영 로직 검증(평일)"""
        # 평일 시나리오: 2099-01-05(월요일) overnight → 2099-01-06(화요일)도 평일
        # NOTE: 2099-01-05: weekday() == 0 → "weekday"
        hour_slots = ["23:00", "00:00", "01:00", "02:00"]

        # 23:00(월) → 10000, 00:00(화) → 15000, 01:00(화) → 15000
        # 10000 + 15000 + 15000 = 40000원
        total_price = service.calculate_total_price(overnight_room, "2099-01-05", hour_slots, available_slots=None)
        assert total_price == 40000

    def test_calculate_total_price_overnight_weekend(self, service, overnight_room):
        """주말 overnight 예약 시 weekday override가 적용되지 않음을 검증.

        Rationale:
            test_calculate_total_price_overnight의 대칭 케이스.
            day_type: 'weekday' override가 주말 날짜에는 매칭되지 않아야 하므로,
            익일 새벽 슬롯(00:00, 01:00)이 default 요금을 유지하는지 검증함.
            _get_day_type()이 weekday/weekend를 실제로 구분하는지 확인하는 유일한 테스트.
        """
        # 주말 시나리오: 2099-01-03(토요일) overnight → 2099-01-04(일요일)
        # NOTE: 기준일·익일 모두 주말이므로 weekday override는 한 슬롯도 적용되지 않음.
        #       2099-01-03: weekday() == 5 → "weekend"
        hour_slots = ["23:00", "00:00", "01:00", "02:00"]

        # 23:00(토) → 10000, 00:00(일) → 10000, 01:00(일) → 10000
        # 10000 + 10000 + 10000 = 30000원
        total_price = service.calculate_total_price(overnight_room, "2099-01-03", hour_slots, available_slots=None)
        assert total_price == 30000

    def test_calculate_total_price_overnight_boundary_weekend_to_weekday(self, service, overnight_room):
        """일요일 overnight → 월요일 새벽: 자정 기준으로 day_type이 전환되는 경계 케이스 검증.

        Rationale:
            calculate_total_price는 자정을 넘는 순간 current_date를 익일로 갱신하는데,
            일요일(weekend)→월요일(weekday) overnight이라면 같은 예약 안에서
            23:00 슬롯은 weekend(override 미적용), 00:00·01:00 슬롯은 weekday(override 적용)가 되어야 함.
            이 경계 전환이 _get_day_type()의 current_date 갱신과 맞물려 정확히 동작하는지 확인함.
        """
        # 2099-01-04(일요일) overnight → 2099-01-05(월요일)
        # NOTE: 2099-01-04: weekday() == 6 → "weekend", 2099-01-05: weekday() == 0 → "weekday"
        hour_slots = ["23:00", "00:00", "01:00", "02:00"]

        # 23:00(일, weekend) → 10000
        # 00:00(월, weekday) → 15000
        # 01:00(월, weekday) → 15000
        # 10000 + 15000 + 15000 = 40000원
        total_price = service.calculate_total_price(overnight_room, "2099-01-04", hour_slots, available_slots=None)
        assert total_price == 40000

    def test_calculate_total_price_overnight_boundary_weekday_to_weekend(self, service, overnight_room):
        """금요일 overnight → 토요일 새벽: 자정 기준으로 weekday→weekend 전환 케이스 검증.

        Rationale:
            일요일→월요일의 역방향 케이스.
            23:00 슬롯은 금요일(weekday, override 적용), 자정 이후 슬롯은
            토요일(weekend, override 미적용)이 되어야 함.
            이 비대칭 결과를 통해 _get_day_type()의 current_date 반영이 정확한지 검증함.
        """
        # 2099-01-02(금요일) overnight → 2099-01-03(토요일)
        # NOTE: 2099-01-02: weekday() == 4 → "weekday", 2099-01-03: weekday() == 5 → "weekend"
        hour_slots = ["23:00", "00:00", "01:00", "02:00"]

        # 23:00(금, weekday) → 10000  (00~06 범위 미해당)
        # 00:00(토, weekend) → 10000  (override 미적용)
        # 01:00(토, weekend) → 10000
        # 10000 + 10000 + 10000 = 30000원
        total_price = service.calculate_total_price(overnight_room, "2099-01-02", hour_slots, available_slots=None)
        assert total_price == 30000


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
        svc = AvailabilityService({"naver": mock_crawler})
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

    @pytest.mark.asyncio
    async def test_full_flow_partial_availability(self, service, mock_crawler, mock_pricing_service):
        """is_partial 상태일 때 check_availability의 응답에 estimated_price가 정상적으로 포함되는지 검증"""
        # Given
        req = AvailabilityRequest(
            date=FUTURE_DATE, capacity=3, start_hour="14:00", end_hour="16:00",
            swLat=37.0, swLng=126.0, neLat=38.0, neLng=127.0
        )
        
        # Room setup
        mock_room = RoomDetail(
            name="MockRoom", branch="MockBranch", business_id="b1", biz_item_id="r1",
            pricePerHour=10000, max_capacity=10,
            can_reserve_one_hour=True, requiresContactOnSameDay=False,
            recommend_capacity_range=[4, 8], price_config={"default": 10000}
        )

        # Partial availability = available is False, but available_slots has some True
        mock_crawler_result = RoomAvailability(
            room_detail=mock_room,
            available=False,
            available_slots={"14:00": True, "15:00": False}
        )
        mock_crawler.check_availability.return_value = [mock_crawler_result]
        
        # Mock actual price calculation inside `calculate_total_price` if needed, 
        # but check_availability calls calculate_total_price if estimated_price is not provided by crawler.
        with mock.patch.object(service, "calculate_total_price", return_value=15000) as mock_calc:
            # When
            with patch("app.services.availability_service.get_rooms_by_criteria") as mock_db, \
                 patch("app.services.availability_service.filter_rooms_by_type", return_value=[mock_room]), \
                 patch("app.services.availability_service.validate_availability_request"):
                mock_db.return_value = [mock_room]
                response = await service.check_availability(req)

            # Then
            # Should have handled it properly
            mock_calc.assert_called_once()
            
            assert len(response.branches) == 1
            branch = response.branches[0]
            assert len(branch.rooms) == 1
            res = branch.rooms[0]

            assert res.name == "MockRoom"
            assert res.available is False
            assert res.estimated_price == 15000


    @pytest.mark.asyncio
    async def test_full_flow_partial_availability_with_error(self, service, mock_crawler, mock_pricing_service):
        """is_partial 상태일 때 요금 계산(calculate_total_price)에서 예외 발생 시,
        예외 없이 graceful하게 처리되고 min_price_partial이 갱신되지 않으므로
        지점이 응답에서 제외되어야 함을 검증."""
        # Given
        req = AvailabilityRequest(
            date=FUTURE_DATE, capacity=3, start_hour="14:00", end_hour="16:00",
            swLat=37.0, swLng=126.0, neLat=38.0, neLng=127.0
        )
        
        # Room setup
        mock_room = RoomDetail(
            name="MockRoom", branch="MockBranch", business_id="b1", biz_item_id="r1",
            pricePerHour=10000, max_capacity=10,
            can_reserve_one_hour=True, requiresContactOnSameDay=False,
            recommend_capacity_range=[4, 8], price_config={"default": 10000}
        )

        mock_crawler_result = RoomAvailability(
            room_detail=mock_room,
            available=False,
            available_slots={"14:00": True, "15:00": False}
        )
        mock_crawler.check_availability.return_value = [mock_crawler_result]
        
        with mock.patch.object(service, "calculate_total_price", side_effect=ValueError("Calc Error")) as mock_calc:
            # When
            with patch("app.services.availability_service.get_rooms_by_criteria") as mock_db, \
                 patch("app.services.availability_service.filter_rooms_by_type", return_value=[mock_room]), \
                 patch("app.services.availability_service.validate_availability_request"):
                mock_db.return_value = [mock_room]
                
                # Exception should be caught and not thrown
                response = await service.check_availability(req)

            # Then: 예외가 발생해도 서버 에러는 없어야 함
            assert mock_calc.call_count == 2

            # is_partial이지만 가격 계산 실패(estimated_price=None) → min_price_partial=None
            # → 즉시/부분 가능 기준 모두 충족하지 못해 지점이 응답에서 제외됨
            assert len(response.branches) == 0, (
                "가격 계산 실패로 min_price_partial이 None인 경우, "
                "부분 가능 지점도 응답에서 제외되어야 함"
            )


    @pytest.mark.asyncio
    async def test_aggregate_min_price_by_available_status(self, service, mock_crawler):
        """branch(지점)별 min_price_available 및 min_price_partial 집계 검증"""
        # Given
        req = AvailabilityRequest(
            date=FUTURE_DATE, capacity=3, start_hour="14:00", end_hour="16:00",
            swLat=37.0, swLng=126.0, neLat=38.0, neLng=127.0
        )

        branch_id = "branch_multi"

        # 방 1: 완전 예약 가능 (available=True), 2시간 기준 20000원 -> min_price_available 후보
        room1 = RoomDetail(
            name="Room1", branch="Branch", business_id=branch_id, biz_item_id="r1",
            pricePerHour=10000, max_capacity=10,
            can_reserve_one_hour=True, requiresContactOnSameDay=False,
            recommend_capacity_range=[4, 8], priceConfig={}
        )
        avail_1 = RoomAvailability(
            room_detail=room1, available=True, available_slots={"14:00": True, "15:00": True}
        )

        # 방 2: 부분 예약 가능 (available=False), 예약가능한 1시간 기준 7500원 -> min_price_partial 후보
        room2 = RoomDetail(
            name="Room2", branch="Branch", business_id=branch_id, biz_item_id="r2",
            pricePerHour=7500, max_capacity=10,
            can_reserve_one_hour=True, requiresContactOnSameDay=False,
            recommend_capacity_range=[4, 8], priceConfig={}
        )
        avail_2 = RoomAvailability(
            room_detail=room2, available=False, available_slots={"14:00": True, "15:00": False},
            estimated_price=7500
        )

        # 방 3: 완전 예약 가능 (available=True), 2시간 기준 25000원 -> 최저가가 아니므로 무시됨
        room3 = RoomDetail(
            name="Room3", branch="Branch", business_id=branch_id, biz_item_id="r3",
            pricePerHour=12500, max_capacity=10,
            can_reserve_one_hour=True, requiresContactOnSameDay=False,
            recommend_capacity_range=[4, 8], priceConfig={}
        )
        avail_3 = RoomAvailability(
            room_detail=room3, available=True, available_slots={"14:00": True, "15:00": True}
        )

        # 방 4: 예약 불가 (available=False) -> 집계 제외
        room4 = RoomDetail(
            name="Room4", branch="Branch", business_id=branch_id, biz_item_id="r4",
            pricePerHour=5000, max_capacity=10,
            can_reserve_one_hour=True, requiresContactOnSameDay=False,
            recommend_capacity_range=[4, 8], priceConfig={}
        )
        avail_4 = RoomAvailability(
            room_detail=room4, available=False, available_slots={"14:00": False, "15:00": False}
        )

        mock_crawler.check_availability.return_value = [avail_1, avail_2, avail_3, avail_4]

        # When
        with patch("app.services.availability_service.get_rooms_by_criteria") as mock_db, \
             patch("app.services.availability_service.filter_rooms_by_type", return_value=[room1, room2, room3, room4]), \
             patch("app.services.availability_service.validate_availability_request"):
            mock_db.return_value = [room1, room2, room3, room4]
            response = await service.check_availability(req)

        # Then
        assert len(response.branches) == 1
        branch = response.branches[0]
        
        # 예약 가능한 방만 응답에 포함되므로 room4는 제외됨 (총 3개)
        assert len(branch.rooms) == 3
        
        # 최저가 집계 검증
        assert branch.min_price_available == 20000
        assert branch.min_price_partial == 7500

    @pytest.mark.asyncio
    async def test_aggregate_min_price_only_available_rooms(self, service, mock_crawler):
        req = AvailabilityRequest(
            date=FUTURE_DATE, capacity=3, start_hour="14:00", end_hour="16:00",
            swLat=37.0, swLng=126.0, neLat=38.0, neLng=127.0
        )
        room1 = RoomDetail(
            name="Room1", branch="Branch", business_id="b1", biz_item_id="r1",
            pricePerHour=10000, max_capacity=10, can_reserve_one_hour=True, requiresContactOnSameDay=False,
            recommend_capacity_range=[4, 8], priceConfig={}
        )
        avail_1 = RoomAvailability(
            room_detail=room1, available=True, available_slots={"14:00": True, "15:00": True}, estimated_price=20000
        )
        
        mock_crawler.check_availability.return_value = [avail_1]
        
        with patch("app.services.availability_service.get_rooms_by_criteria") as mock_db, \
             patch("app.services.availability_service.filter_rooms_by_type", return_value=[room1]), \
             patch("app.services.availability_service.validate_availability_request"):
            mock_db.return_value = [room1]
            response = await service.check_availability(req)

        branch = response.branches[0]
        assert branch.min_price_partial is None
        assert branch.min_price_available == 20000

    @pytest.mark.asyncio
    async def test_aggregate_min_price_only_partial_rooms(self, service, mock_crawler):
        req = AvailabilityRequest(
            date=FUTURE_DATE, capacity=3, start_hour="14:00", end_hour="16:00",
            swLat=37.0, swLng=126.0, neLat=38.0, neLng=127.0
        )
        room1 = RoomDetail(
            name="Room1", branch="Branch", business_id="b1", biz_item_id="r1",
            pricePerHour=10000, max_capacity=10, can_reserve_one_hour=True, requiresContactOnSameDay=False,
            recommend_capacity_range=[4, 8], priceConfig={}
        )
        avail_1 = RoomAvailability(
            room_detail=room1, available=False, available_slots={"14:00": True, "15:00": False}, estimated_price=10000
        )
        
        mock_crawler.check_availability.return_value = [avail_1]
        
        with patch("app.services.availability_service.get_rooms_by_criteria") as mock_db, \
             patch("app.services.availability_service.filter_rooms_by_type", return_value=[room1]), \
             patch("app.services.availability_service.validate_availability_request"):
            mock_db.return_value = [room1]
            response = await service.check_availability(req)

        branch = response.branches[0]
        assert branch.min_price_available is None
        assert branch.min_price_partial == 10000

    @pytest.mark.asyncio
    async def test_aggregate_min_price_no_available_rooms(self, service, mock_crawler):
        req = AvailabilityRequest(
            date=FUTURE_DATE, capacity=3, start_hour="14:00", end_hour="16:00",
            swLat=37.0, swLng=126.0, neLat=38.0, neLng=127.0
        )
        room1 = RoomDetail(
            name="Room1", branch="Branch", business_id="b1", biz_item_id="r1",
            pricePerHour=10000, max_capacity=10, can_reserve_one_hour=True, requiresContactOnSameDay=False,
            recommend_capacity_range=[4, 8], priceConfig={}
        )
        avail_1 = RoomAvailability(
            room_detail=room1, available=False, available_slots={"14:00": False, "15:00": False}, estimated_price=0
        )
        
        mock_crawler.check_availability.return_value = [avail_1]
        
        with patch("app.services.availability_service.get_rooms_by_criteria") as mock_db, \
             patch("app.services.availability_service.filter_rooms_by_type", return_value=[room1]), \
             patch("app.services.availability_service.validate_availability_request"):
            mock_db.return_value = [room1]
            response = await service.check_availability(req)
        assert len(response.branches) == 0


class TestBranchFiltering:
    """available_count == 0 지점 응답 제외 검증."""

    @pytest.fixture
    def service(self):
        svc = AvailabilityService({})
        svc.pricing_service = MagicMock()
        return svc

    @pytest.fixture
    def mock_crawler(self):
        return AsyncMock()

    @pytest.mark.asyncio
    async def test_branch_excluded_when_all_rooms_unavailable(self, service, mock_crawler):
        """모든 룸이 예약 불가(available=False)인 지점은 응답 branches에서 제외되어야 함."""
        service.crawlers_map = {"naver": mock_crawler}

        req = AvailabilityRequest(
            date=FUTURE_DATE, capacity=1, start_hour="14:00", end_hour="16:00",
            swLat=37.0, swLng=126.0, neLat=38.0, neLng=127.0
        )
        room = RoomDetail(
            name="Room", branch="Branch", business_id="bid1", biz_item_id="r1",
            pricePerHour=10000, max_capacity=10, can_reserve_one_hour=True,
            requiresContactOnSameDay=False, recommend_capacity_range=[4, 8]
        )
        avail = RoomAvailability(
            room_detail=room, available=False,
            available_slots={"14:00": False, "15:00": False}
        )
        mock_crawler.check_availability.return_value = [avail]

        with patch("app.services.availability_service.get_rooms_by_criteria") as mock_db, \
             patch("app.services.availability_service.filter_rooms_by_type", return_value=[room]), \
             patch("app.services.availability_service.validate_availability_request"):
            mock_db.return_value = [room]
            response = await service.check_availability(req)

        assert len(response.branches) == 0, "모든 룸이 예약 불가이면 지점 자체가 응답에서 제외되어야 함"

    @pytest.mark.asyncio
    async def test_branch_included_when_at_least_one_room_available(self, service, mock_crawler):
        """한 지점에서 하나라도 예약 가능한 룸이 있으면 지점이 응답에 포함되어야 함."""
        service.crawlers_map = {"naver": mock_crawler}

        req = AvailabilityRequest(
            date=FUTURE_DATE, capacity=1, start_hour="14:00", end_hour="16:00",
            swLat=37.0, swLng=126.0, neLat=38.0, neLng=127.0
        )
        room_ok = RoomDetail(
            name="RoomOK", branch="Branch", business_id="bid1", biz_item_id="r1",
            pricePerHour=15000, max_capacity=10, can_reserve_one_hour=True,
            requiresContactOnSameDay=False, recommend_capacity_range=[4, 8]
        )
        room_no = RoomDetail(
            name="RoomNo", branch="Branch", business_id="bid1", biz_item_id="r2",
            pricePerHour=15000, max_capacity=10, can_reserve_one_hour=True,
            requiresContactOnSameDay=False, recommend_capacity_range=[4, 8]
        )
        avail_ok = RoomAvailability(
            room_detail=room_ok, available=True,
            available_slots={"14:00": True, "15:00": True}, estimated_price=30000
        )
        avail_no = RoomAvailability(
            room_detail=room_no, available=False,
            available_slots={"14:00": False, "15:00": False}
        )
        mock_crawler.check_availability.return_value = [avail_ok, avail_no]

        with patch("app.services.availability_service.get_rooms_by_criteria") as mock_db, \
             patch("app.services.availability_service.filter_rooms_by_type", return_value=[room_ok, room_no]), \
             patch("app.services.availability_service.validate_availability_request"):
            mock_db.return_value = [room_ok, room_no]
            response = await service.check_availability(req)

        assert len(response.branches) == 1, "예약 가능 룸이 있는 지점은 포함되어야 함"
        assert response.branches[0].available_count == 1

    @pytest.mark.asyncio
    async def test_available_count_does_not_include_partial(self, service, mock_crawler):
        """부분 가능(is_partial) 룸은 available=False지만 응답에는 포함되고 available_count에는 미집계."""
        service.crawlers_map = {"naver": mock_crawler}

        req = AvailabilityRequest(
            date=FUTURE_DATE, capacity=1, start_hour="14:00", end_hour="16:00",
            swLat=37.0, swLng=126.0, neLat=38.0, neLng=127.0
        )
        room_full = RoomDetail(
            name="Full", branch="Branch", business_id="bid1", biz_item_id="r1",
            pricePerHour=15000, max_capacity=10, can_reserve_one_hour=True,
            requiresContactOnSameDay=False, recommend_capacity_range=[4, 8]
        )
        room_partial = RoomDetail(
            name="Partial", branch="Branch", business_id="bid1", biz_item_id="r2",
            pricePerHour=15000, max_capacity=10, can_reserve_one_hour=True,
            requiresContactOnSameDay=False, recommend_capacity_range=[4, 8]
        )
        avail_full = RoomAvailability(
            room_detail=room_full, available=True,
            available_slots={"14:00": True, "15:00": True}, estimated_price=30000
        )
        # available=False이지만 일부 슬롯이 True → is_partial
        avail_partial = RoomAvailability(
            room_detail=room_partial, available=False,
            available_slots={"14:00": True, "15:00": False}, estimated_price=15000
        )
        mock_crawler.check_availability.return_value = [avail_full, avail_partial]

        with patch("app.services.availability_service.get_rooms_by_criteria") as mock_db, \
             patch("app.services.availability_service.filter_rooms_by_type", return_value=[room_full, room_partial]), \
             patch("app.services.availability_service.validate_availability_request"):
            mock_db.return_value = [room_full, room_partial]
            response = await service.check_availability(req)

        assert len(response.branches) == 1
        # 전체 예약 가능(r1)만 available_count에 집계, 부분 가능(r2)은 미집계
        assert response.branches[0].available_count == 1
        room_ids = {r.biz_item_id for r in response.branches[0].rooms}
        assert "r2" in room_ids, "부분 가능 룸은 응답에는 포함되어야 함"

    @pytest.mark.asyncio
    async def test_cache_hit_regression(self, service, mock_crawler):
        """동일한 요청을 두 번 보낼 때, 크롤러는 한 번만 호출되고 두 번째는 캐시를 사용하는지 검증."""
        service.crawlers_map = {"naver": mock_crawler}
        
        req = AvailabilityRequest(
            date=FUTURE_DATE, capacity=2, start_hour="14:00", end_hour="16:00",
            swLat=37.0, swLng=126.0, neLat=38.0, neLng=127.0
        )
        room = RoomDetail(
            name="CacheTest", branch="Branch", business_id="b1", biz_item_id="r1",
            pricePerHour=10000, max_capacity=10, can_reserve_one_hour=True,
            requiresContactOnSameDay=False, recommend_capacity_range=[4, 8]
        )
        avail = RoomAvailability(
            room_detail=room, available=True,
            available_slots={"14:00": True, "15:00": True}, estimated_price=20000
        )
        
        # 첫 번째 호출에서는 크롤러가 결과를 반환하도록 설정
        mock_crawler.check_availability.return_value = [avail]
        
        with patch("app.services.availability_service.get_rooms_by_criteria", return_value=[room]), \
             patch("app.services.availability_service.validate_availability_request"):
            
            # 1. 첫 번째 호출 (Cache Miss)
            resp1 = await service.check_availability(req)
            assert mock_crawler.check_availability.call_count == 1, "첫 번째 호출에서 크롤러가 호출되어야 함"
            
            # 2. 두 번째 호출 (Cache Hit)
            resp2 = await service.check_availability(req)
            
            # 크롤러 호출 횟수가 여전히 1이어야 함 (두 번째는 캐시 사용)
            assert mock_crawler.check_availability.call_count == 1, "두 번째 호출에서 캐시가 사용되어 크롤러 호출이 늘어나지 않아야 함"
            
            assert resp2.has_cached_data is True
            assert resp1.available_biz_item_ids == resp2.available_biz_item_ids
            assert len(resp1.branches) == len(resp2.branches)
            assert resp1.branches[0].rooms[0].name == resp2.branches[0].rooms[0].name

