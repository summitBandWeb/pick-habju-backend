"""시간대별 variant room 병합 테스트.

비쥬 합주실처럼 같은 물리적 방이 '블랙룸', '블랙룸 (평일 낮)', '블랙룸 (심야)' 등
여러 room으로 쪼개져 있을 때, API 응답에서 하나로 병합하는 로직을 검증한다.
"""

import pytest
from app.services.availability_service import AvailabilityService, _TIME_QUALIFIER_RE
from app.models.dto import RoomAvailability, RoomDetail, PolicyWarning


@pytest.fixture
def service():
    return AvailabilityService({})


def _make_room_detail(
    name: str,
    business_id: str = "biz1",
    biz_item_id: str = "item1",
    **kwargs,
) -> RoomDetail:
    defaults = dict(
        branch="테스트지점",
        pricePerHour=10000,
        can_reserve_one_hour=True,
        requiresContactOnSameDay=False,
        max_capacity=10,
        recommend_capacity_range=[3, 5],
    )
    defaults.update(kwargs)
    return RoomDetail(
        name=name,
        business_id=business_id,
        biz_item_id=biz_item_id,
        **defaults,
    )


def _make_avail(
    room_detail: RoomDetail,
    available_slots: dict,
    available: bool = True,
    estimated_price: int | None = None,
    policy_warnings: list | None = None,
) -> RoomAvailability:
    return RoomAvailability(
        room_detail=room_detail,
        available=available,
        available_slots=available_slots,
        estimated_price=estimated_price,
        policy_warnings=policy_warnings or [],
    )


# ──────────────────────────────────────────────
# Phase 1: base name 추출
# ──────────────────────────────────────────────


class TestGetBaseRoomName:

    def test_strip_weekday_daytime(self):
        assert AvailabilityService._get_base_room_name("블랙룸 (평일 낮)") == "블랙룸"

    def test_strip_late_night(self):
        assert AvailabilityService._get_base_room_name("블랙룸 (심야)") == "블랙룸"

    def test_strip_weekend_holiday(self):
        assert AvailabilityService._get_base_room_name("C룸 (주말/공휴일)") == "C룸"

    def test_strip_weekday(self):
        assert AvailabilityService._get_base_room_name("A룸 (평일)") == "A룸"

    def test_strip_weekend(self):
        assert AvailabilityService._get_base_room_name("A룸 (주말)") == "A룸"

    def test_strip_night(self):
        assert AvailabilityService._get_base_room_name("레드룸 (야간)") == "레드룸"

    def test_strip_weekday_morning(self):
        assert AvailabilityService._get_base_room_name("스튜디오 (평일 오전)") == "스튜디오"

    def test_strip_weekday_night(self):
        assert AvailabilityService._get_base_room_name("스튜디오 (평일 야간)") == "스튜디오"

    def test_strip_daytime(self):
        assert AvailabilityService._get_base_room_name("B룸 (주간)") == "B룸"

    def test_strip_holiday(self):
        assert AvailabilityService._get_base_room_name("D룸 (공휴일)") == "D룸"

    def test_no_qualifier_unchanged(self):
        assert AvailabilityService._get_base_room_name("A룸") == "A룸"

    def test_non_time_parenthetical_unchanged(self):
        """시간 한정어가 아닌 괄호는 제거하지 않음"""
        assert AvailabilityService._get_base_room_name("블랙룸 (2인)") == "블랙룸 (2인)"

    def test_empty_string(self):
        assert AvailabilityService._get_base_room_name("") == ""


# ──────────────────────────────────────────────
# Phase 2: 병합 로직
# ──────────────────────────────────────────────


class TestMergeTimeVariantRooms:

    def test_single_room_passthrough(self, service):
        """variant가 1개면 병합 없이 통과"""
        room = _make_room_detail("A룸", biz_item_id="item1")
        avail = _make_avail(room, {"14:00": True, "15:00": True}, estimated_price=20000)

        result = service._merge_time_variant_rooms([avail])

        assert len(result) == 1
        assert result[0].room_detail.name == "A룸"
        assert result[0].estimated_price == 20000

    def test_merge_two_variants(self, service):
        """같은 branch + base name의 2개 variant → 1개로 병합"""
        room_day = _make_room_detail("블랙룸 (평일 낮)", biz_item_id="day1")
        room_night = _make_room_detail("블랙룸 (심야)", biz_item_id="night1")

        avail_day = _make_avail(
            room_day,
            {"14:00": True, "15:00": True, "22:00": False},
            estimated_price=20000,
        )
        avail_night = _make_avail(
            room_night,
            {"14:00": False, "15:00": False, "22:00": True},
            estimated_price=15000,
        )

        result = service._merge_time_variant_rooms([avail_day, avail_night])

        assert len(result) == 1
        merged = result[0]
        assert merged.room_detail.name == "블랙룸"
        # available_slots union
        assert merged.available_slots["14:00"] is True
        assert merged.available_slots["15:00"] is True
        assert merged.available_slots["22:00"] is True
        # price 합산
        assert merged.estimated_price == 35000
        # all slots True → available=True
        assert merged.available is True

    def test_merge_three_variants(self, service):
        """3개 variant (기본 + 평일 낮 + 심야) → 1개로 병합"""
        room_base = _make_room_detail("블랙룸", biz_item_id="base1")
        room_day = _make_room_detail("블랙룸 (평일 낮)", biz_item_id="day1")
        room_night = _make_room_detail("블랙룸 (심야)", biz_item_id="night1")

        avail_base = _make_avail(
            room_base,
            {"18:00": True, "19:00": True},
            estimated_price=30000,
        )
        avail_day = _make_avail(
            room_day,
            {"18:00": False, "19:00": False},
            available=False,
            estimated_price=None,
        )
        avail_night = _make_avail(
            room_night,
            {"18:00": False, "19:00": False},
            available=False,
            estimated_price=None,
        )

        result = service._merge_time_variant_rooms([avail_base, avail_day, avail_night])

        assert len(result) == 1
        merged = result[0]
        assert merged.room_detail.name == "블랙룸"
        assert merged.room_detail.biz_item_id == "base1"  # base가 available slots 최다
        assert merged.estimated_price == 30000

    def test_primary_picks_most_available(self, service):
        """available slot이 가장 많은 variant의 biz_item_id를 사용"""
        room_day = _make_room_detail("레드룸 (평일 낮)", biz_item_id="day1")
        room_night = _make_room_detail("레드룸 (심야)", biz_item_id="night1")

        avail_day = _make_avail(
            room_day,
            {"14:00": True, "15:00": True, "16:00": True},
            estimated_price=30000,
        )
        avail_night = _make_avail(
            room_night,
            {"14:00": False, "15:00": False, "16:00": False},
            available=False,
        )

        result = service._merge_time_variant_rooms([avail_day, avail_night])

        assert result[0].room_detail.biz_item_id == "day1"

    def test_different_branch_not_merged(self, service):
        """다른 business_id면 같은 base name이어도 병합 안 됨"""
        room1 = _make_room_detail(
            "블랙룸 (평일 낮)", business_id="biz1", biz_item_id="item1"
        )
        room2 = _make_room_detail(
            "블랙룸 (심야)", business_id="biz2", biz_item_id="item2"
        )

        avail1 = _make_avail(room1, {"14:00": True}, estimated_price=10000)
        avail2 = _make_avail(room2, {"22:00": True}, estimated_price=15000)

        result = service._merge_time_variant_rooms([avail1, avail2])

        assert len(result) == 2

    def test_no_qualifier_same_name_not_merged(self, service):
        """한정어가 없는 동일 이름 room은 병합하지 않음 (안전장치)"""
        room1 = _make_room_detail("블랙룸", biz_item_id="item1")
        room2 = _make_room_detail("블랙룸", biz_item_id="item2")

        avail1 = _make_avail(room1, {"14:00": True}, estimated_price=10000)
        avail2 = _make_avail(room2, {"15:00": True}, estimated_price=10000)

        result = service._merge_time_variant_rooms([avail1, avail2])

        # 한정어가 없으므로 병합 안 됨
        assert len(result) == 2

    def test_partial_availability_after_merge(self, service):
        """병합 후 일부 슬롯만 True면 available=False (partial)"""
        room_day = _make_room_detail("블랙룸 (평일 낮)", biz_item_id="day1")
        room_night = _make_room_detail("블랙룸 (심야)", biz_item_id="night1")

        avail_day = _make_avail(
            room_day,
            {"14:00": True, "15:00": False},
            available=False,
            estimated_price=10000,
        )
        avail_night = _make_avail(
            room_night,
            {"14:00": False, "15:00": False},
            available=False,
        )

        result = service._merge_time_variant_rooms([avail_day, avail_night])

        assert len(result) == 1
        assert result[0].available is False  # not all slots True
        assert result[0].available_slots["14:00"] is True  # union
        assert result[0].available_slots["15:00"] is False

    def test_policy_warnings_deduplicated(self, service):
        """병합 시 policy_warnings type 기준 중복 제거"""
        room_day = _make_room_detail("블랙룸 (평일 낮)", biz_item_id="day1")
        room_night = _make_room_detail("블랙룸 (심야)", biz_item_id="night1")

        warn1 = PolicyWarning(type="min_hours_violation", message="최소 2시간")
        warn2 = PolicyWarning(type="min_hours_violation", message="최소 2시간")
        warn3 = PolicyWarning(type="call_required_today", message="당일 전화")

        avail_day = _make_avail(
            room_day,
            {"14:00": True},
            estimated_price=10000,
            policy_warnings=[warn1],
        )
        avail_night = _make_avail(
            room_night,
            {"22:00": True},
            estimated_price=15000,
            policy_warnings=[warn2, warn3],
        )

        result = service._merge_time_variant_rooms([avail_day, avail_night])

        warnings = result[0].policy_warnings
        types = [w.type for w in warnings]
        assert types == ["min_hours_violation", "call_required_today"]

    def test_mixed_rooms_some_merged(self, service):
        """병합 대상과 비대상이 섞여있을 때 올바르게 처리"""
        # 병합 대상
        room_day = _make_room_detail("블랙룸 (평일 낮)", biz_item_id="day1")
        room_night = _make_room_detail("블랙룸 (심야)", biz_item_id="night1")
        # 병합 비대상
        room_other = _make_room_detail("A룸", biz_item_id="other1")

        avail_day = _make_avail(room_day, {"14:00": True}, estimated_price=10000)
        avail_night = _make_avail(room_night, {"22:00": True}, estimated_price=15000)
        avail_other = _make_avail(room_other, {"14:00": True}, estimated_price=20000)

        result = service._merge_time_variant_rooms([avail_day, avail_night, avail_other])

        assert len(result) == 2
        names = sorted(r.room_detail.name for r in result)
        assert names == ["A룸", "블랙룸"]

    def test_all_none_prices(self, service):
        """모든 variant의 estimated_price가 None이면 병합 결과도 None"""
        room_day = _make_room_detail("블랙룸 (평일 낮)", biz_item_id="day1")
        room_night = _make_room_detail("블랙룸 (심야)", biz_item_id="night1")

        avail_day = _make_avail(
            room_day, {"14:00": False}, available=False, estimated_price=None
        )
        avail_night = _make_avail(
            room_night, {"14:00": False}, available=False, estimated_price=None
        )

        result = service._merge_time_variant_rooms([avail_day, avail_night])

        assert result[0].estimated_price is None
