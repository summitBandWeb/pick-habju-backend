# tests/services/test_room_collection_day_variant_merge.py
"""
RoomCollectionService 요일 variant 병합 로직 단위 테스트 (#259)

테스트 대상:
- _get_base_room_name
- _classify_day_variant
- _merge_day_variant_rooms

실행: pytest tests/services/test_room_collection_day_variant_merge.py -v
"""

import pytest
from unittest.mock import patch


@pytest.fixture
def service():
    with patch("app.services.room_collection_service.NaverMapCrawler"), \
         patch("app.services.room_collection_service.NaverRoomFetcher"), \
         patch("app.services.room_collection_service.RoomParserService"), \
         patch("app.services.room_collection_service.get_supabase_client"):
        from app.services.room_collection_service import RoomCollectionService
        return RoomCollectionService()


def _room(biz_item_id: str, name: str, price: int = 10000) -> dict:
    return {"bizItemId": biz_item_id, "name": name, "price": price}


def _parsed(clean_name: str, day_type=None, max_cap=5, rec_cap=3, price_config=None) -> dict:
    return {
        "clean_name": clean_name,
        "day_type": day_type,
        "max_capacity": max_cap,
        "recommend_capacity": rec_cap,
        "recommend_capacity_range": [rec_cap - 1, rec_cap + 1],
        "price_config": price_config if price_config is not None else {},
    }


# ── _get_base_room_name ────────────────────────────────────────────────────────

class TestGetBaseRoomName:
    def test_strips_weekday_suffix(self, service):
        assert service._get_base_room_name("1번룸 (평일 낮)") == "1번룸"

    def test_strips_weekend_suffix(self, service):
        assert service._get_base_room_name("1번룸 (주말)") == "1번룸"

    def test_strips_time_only_suffix(self, service):
        assert service._get_base_room_name("1번룸 (심야)") == "1번룸"

    def test_no_suffix_unchanged(self, service):
        assert service._get_base_room_name("1번룸") == "1번룸"

    def test_empty_string(self, service):
        assert service._get_base_room_name("") == ""


# ── _classify_day_variant ──────────────────────────────────────────────────────

class TestClassifyDayVariant:
    def test_day_type_weekday(self, service):
        assert service._classify_day_variant("1번룸", "weekday") == "weekday"

    def test_day_type_weekend(self, service):
        assert service._classify_day_variant("1번룸", "weekend") == "weekend"

    def test_weekday_suffix_no_day_type(self, service):
        assert service._classify_day_variant("1번룸 (평일 낮)", None) == "weekday"

    def test_weekend_suffix_no_day_type(self, service):
        assert service._classify_day_variant("1번룸 (주말)", None) == "weekend"

    def test_time_only_suffix_returns_none(self, service):
        """심야/야간/주간은 요일 정보 없음 → 병합 대상 제외"""
        assert service._classify_day_variant("1번룸 (심야)", None) is None
        assert service._classify_day_variant("1번룸 (야간)", None) is None
        assert service._classify_day_variant("1번룸 (주간)", None) is None

    def test_no_suffix_no_day_type_returns_none(self, service):
        assert service._classify_day_variant("1번룸", None) is None


# ── _merge_day_variant_rooms ───────────────────────────────────────────────────

class TestMergeDayVariantRooms:

    def test_normal_merge_weekday_weekend(self, service):
        """정상 병합: weekday 1 + weekend 1 → 단일 룸"""
        rooms = [
            _room("wd-1", "[평일 낮] 1번룸", price=10000),
            _room("we-1", "[주말] 1번룸", price=15000),
        ]
        parsed = {
            "wd-1": _parsed("1번룸 (평일 낮)", day_type=None, max_cap=5),
            "we-1": _parsed("1번룸", day_type="weekend", max_cap=5),
        }
        merged_rooms, merged_parsed, dropped_ids = service._merge_day_variant_rooms(rooms, parsed)

        assert len(merged_rooms) == 1
        assert merged_rooms[0]["bizItemId"] == "wd-1"
        assert merged_parsed["wd-1"]["clean_name"] == "1번룸"
        assert merged_parsed["wd-1"]["day_type"] is None
        assert dropped_ids == ["we-1"]

    def test_price_config_weekend_override_added(self, service):
        """주말 가격이 다를 때 weekend override가 price_config에 추가됨"""
        rooms = [
            _room("wd-1", "[평일 낮] 1번룸", price=10000),
            _room("we-1", "[주말] 1번룸", price=15000),
        ]
        parsed = {
            "wd-1": _parsed("1번룸 (평일 낮)", day_type=None),
            "we-1": _parsed("1번룸", day_type="weekend"),
        }
        _, merged_parsed, _ = service._merge_day_variant_rooms(rooms, parsed)
        cfg = merged_parsed["wd-1"]["price_config"]

        assert cfg["default"] == 10000
        weekend_override = next(o for o in cfg["overrides"] if o["day_type"] == "weekend")
        assert weekend_override["price"] == 15000

    def test_existing_surcharges_preserved(self, service):
        """기존 surcharges가 병합 후에도 보존됨"""
        existing_cfg = {
            "default": 10000,
            "overrides": [],
            "surcharges": [{"day_type": "weekday", "amount": 2000}],
        }
        rooms = [
            _room("wd-1", "[평일 낮] 1번룸", price=10000),
            _room("we-1", "[주말] 1번룸", price=15000),
        ]
        parsed = {
            "wd-1": _parsed("1번룸 (평일 낮)", day_type=None, price_config=existing_cfg),
            "we-1": _parsed("1번룸", day_type="weekend"),
        }
        _, merged_parsed, _ = service._merge_day_variant_rooms(rooms, parsed)
        cfg = merged_parsed["wd-1"]["price_config"]

        assert cfg["surcharges"] == [{"day_type": "weekday", "amount": 2000}]

    def test_capacity_takes_higher_value(self, service):
        """주말 max_capacity가 더 높으면 주말 값으로 덮어씀"""
        rooms = [
            _room("wd-1", "[평일 낮] 1번룸", price=10000),
            _room("we-1", "[주말] 1번룸", price=10000),
        ]
        parsed = {
            "wd-1": _parsed("1번룸 (평일 낮)", day_type=None, max_cap=5, rec_cap=3),
            "we-1": _parsed("1번룸", day_type="weekend", max_cap=8, rec_cap=5),
        }
        _, merged_parsed, _ = service._merge_day_variant_rooms(rooms, parsed)

        assert merged_parsed["wd-1"]["max_capacity"] == 8
        assert merged_parsed["wd-1"]["recommend_capacity"] == 5

    def test_recommend_capacity_none_not_overwritten(self, service):
        """주말 recommend_capacity가 None이면 평일 값 유지"""
        rooms = [
            _room("wd-1", "[평일 낮] 1번룸", price=10000),
            _room("we-1", "[주말] 1번룸", price=10000),
        ]
        parsed = {
            "wd-1": _parsed("1번룸 (평일 낮)", day_type=None, max_cap=5, rec_cap=3),
            "we-1": {
                "clean_name": "1번룸",
                "day_type": "weekend",
                "max_capacity": 8,
                "recommend_capacity": None,
                "recommend_capacity_range": None,
                "price_config": {},
            },
        }
        _, merged_parsed, _ = service._merge_day_variant_rooms(rooms, parsed)

        # we_max(8) > wd_max(5)이지만 we_rec=None → recommend_capacity 유지 안 됨 확인
        assert merged_parsed["wd-1"]["max_capacity"] == 8
        assert merged_parsed["wd-1"]["recommend_capacity"] == 3  # 평일 값 유지

    def test_merge_skipped_when_three_variants(self, service):
        """3개 이상 variant → 병합 조건 미충족, 모두 원형 유지"""
        rooms = [
            _room("r-1", "[평일 낮] 1번룸", price=10000),
            _room("r-2", "[주말] 1번룸", price=15000),
            _room("r-3", "1번룸", price=12000),
        ]
        parsed = {
            "r-1": _parsed("1번룸 (평일 낮)", day_type=None),
            "r-2": _parsed("1번룸", day_type="weekend"),
            "r-3": _parsed("1번룸", day_type=None),
        }
        merged_rooms, _merged_parsed, dropped_ids = service._merge_day_variant_rooms(rooms, parsed)

        assert len(merged_rooms) == 3
        assert dropped_ids == []  # 병합 미발생 → 드롭 없음

    def test_no_price_config_when_equal_prices(self, service):
        """평일 == 주말 가격이면 weekend override 미생성"""
        rooms = [
            _room("wd-1", "[평일 낮] 1번룸", price=10000),
            _room("we-1", "[주말] 1번룸", price=10000),
        ]
        parsed = {
            "wd-1": _parsed("1번룸 (평일 낮)", day_type=None),
            "we-1": _parsed("1번룸", day_type="weekend"),
        }
        _, merged_parsed, _ = service._merge_day_variant_rooms(rooms, parsed)
        cfg = merged_parsed["wd-1"]["price_config"]

        assert cfg == {}

    def test_existing_weekday_override_preserved(self, service):
        """기존 weekday override가 병합 후에도 보존됨"""
        existing_cfg = {
            "default": 10000,
            "overrides": [{"day_type": "weekday", "start_hour": "18:00", "end_hour": "24:00", "price": 12000}],
            "surcharges": [],
        }
        rooms = [
            _room("wd-1", "[평일 낮] 1번룸", price=10000),
            _room("we-1", "[주말] 1번룸", price=15000),
        ]
        parsed = {
            "wd-1": _parsed("1번룸 (평일 낮)", day_type=None, price_config=existing_cfg),
            "we-1": _parsed("1번룸", day_type="weekend"),
        }
        _, merged_parsed, _ = service._merge_day_variant_rooms(rooms, parsed)
        cfg = merged_parsed["wd-1"]["price_config"]
        overrides = cfg["overrides"]

        weekday_override = next((o for o in overrides if o["day_type"] == "weekday"), None)
        assert weekday_override is not None
        assert weekday_override["price"] == 12000
        weekend_override = next((o for o in overrides if o["day_type"] == "weekend"), None)
        assert weekend_override is not None
        assert weekend_override["price"] == 15000

    def test_merge_skipped_when_price_missing(self, service):
        """wd_price 또는 we_price가 None이면 price_config 미생성"""
        rooms = [
            _room("wd-1", "[평일 낮] 1번룸", price=0),
            _room("we-1", "[주말] 1번룸", price=15000),
        ]
        rooms[0].pop("price")
        parsed = {
            "wd-1": _parsed("1번룸 (평일 낮)", day_type=None),
            "we-1": _parsed("1번룸", day_type="weekend"),
        }
        _, merged_parsed, _ = service._merge_day_variant_rooms(rooms, parsed)

        # price_config은 원래 평일 값(빈 dict) 유지
        assert merged_parsed["wd-1"].get("price_config") == {}

    def test_three_pairs_six_to_three_rooms(self, service):
        """3개 base_name x (weekday + weekend) = 6룸 → 3룸 병합 (business_id=1227688 시나리오)"""
        rooms = [
            _room("wd-1", "[평일] 1번룸", price=10000),
            _room("we-1", "[주말] 1번룸", price=15000),
            _room("wd-2", "[평일] 2번룸", price=10000),
            _room("we-2", "[주말] 2번룸", price=15000),
            _room("wd-3", "[평일] 3번룸", price=10000),
            _room("we-3", "[주말] 3번룸", price=15000),
        ]
        parsed = {
            "wd-1": _parsed("1번룸 (평일 낮)", day_type=None),
            "we-1": _parsed("1번룸", day_type="weekend"),
            "wd-2": _parsed("2번룸 (평일 낮)", day_type=None),
            "we-2": _parsed("2번룸", day_type="weekend"),
            "wd-3": _parsed("3번룸 (평일 낮)", day_type=None),
            "we-3": _parsed("3번룸", day_type="weekend"),
        }
        merged_rooms, _, dropped_ids = service._merge_day_variant_rooms(rooms, parsed)

        assert len(merged_rooms) == 3
        assert set(r["bizItemId"] for r in merged_rooms) == {"wd-1", "wd-2", "wd-3"}
        assert set(dropped_ids) == {"we-1", "we-2", "we-3"}

    def test_list_price_config_surcharges_not_carried(self, service):
        """기존 price_config가 list 타입이면 surcharges는 [] 처리됨 (list 포맷에는 surcharges 키 없음)"""
        existing_cfg = [
            {"day_type": "weekday", "price_per_hour": 10000},
        ]
        rooms = [
            _room("wd-1", "[평일 낮] 1번룸", price=10000),
            _room("we-1", "[주말] 1번룸", price=15000),
        ]
        parsed = {
            "wd-1": _parsed("1번룸 (평일 낮)", day_type=None, price_config=existing_cfg),
            "we-1": _parsed("1번룸", day_type="weekend"),
        }
        _, merged_parsed, _ = service._merge_day_variant_rooms(rooms, parsed)
        cfg = merged_parsed["wd-1"]["price_config"]

        # list 타입은 isinstance(existing_cfg, dict) = False → surcharges = []
        assert cfg["surcharges"] == []
        # weekend override는 정상 추가됨
        assert any(o.get("day_type") == "weekend" for o in cfg["overrides"])
