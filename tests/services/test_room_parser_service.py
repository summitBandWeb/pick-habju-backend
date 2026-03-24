import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.room_collection_service import RoomCollectionService
from app.services.room_parser_service import RoomParserService


class TestParseWithRegex:
    @pytest.fixture
    def parser(self):
        return RoomParserService()

    def test_basic_parsing_weekday(self, parser):
        result = parser._parse_with_regex("[평일] 블랙룸", "최대 10인 수용 가능")
        assert result["clean_name"] == "블랙룸"
        assert result["day_type"] == "weekday"
        assert result["max_capacity"] == 10

    def test_range_capacity_weekend(self, parser):
        result = parser._parse_with_regex("화이트룸 (주말)", "4~6인 권장, 최대 8인")
        assert result["clean_name"] == "화이트룸"
        assert result["day_type"] == "weekend"
        assert result["recommend_capacity"] == 5
        assert result["max_capacity"] == 8
        assert result["recommend_capacity_range"] == [4, 6]

    def test_extra_charge_parsing(self, parser):
        result = parser._parse_with_regex("스튜디오A", "기본 4인, 1인 추가시 3,000원")
        assert result["base_capacity"] == 4
        assert result["extra_charge"] == 3000

    def test_same_day_call_required(self, parser):
        result = parser._parse_with_regex("레드룸", "당일 예약은 전화 문의 바랍니다")
        assert result["requires_call_on_sameday"] is True

    def test_cannot_reserve_one_hour(self, parser):
        result = parser._parse_with_regex("블루룸", "최소 2시간부터 예약 가능합니다")
        assert result["can_reserve_one_hour"] is False

    def test_empty_description(self, parser):
        result = parser._parse_with_regex("일반룸", "")
        assert result["clean_name"] == "일반룸"
        assert result["day_type"] is None
        assert result["max_capacity"] is None
        assert result["recommend_capacity_range"] is None

    def test_name_capacity_parentheses(self, parser):
        result = parser._parse_with_regex("블랙룸 (정원 13명, 최대 18명)", "")
        assert result["clean_name"] == "블랙룸"
        assert result["max_capacity"] == 18
        assert result["recommend_capacity"] == 13

    def test_paren_dash_capacity(self, parser):
        result = parser._parse_with_regex("R룸 (-15명)", "")
        assert result["clean_name"] == "R룸"
        assert result["max_capacity"] == 15

    def test_equipment_model_false_positive(self, parser):
        result = parser._parse_with_regex("룸A", "Orange OB1-500 Head, Marshall 앰프")
        assert result["max_capacity"] is None

    def test_clean_name_strips_promo_bracket_and_capacity_note(self, parser):
        result = parser._parse_with_regex("[개강특가] 블랙룸 (정원 20명, 최대 30명)", "")
        assert result["clean_name"] == "블랙룸"
        assert result["max_capacity"] == 30
        assert result["recommend_capacity"] == 20

    def test_clean_name_strips_reservation_parenthetical_note(self, parser):
        result = parser._parse_with_regex("Room A (예약 시 오전, 오후 확인)", "")
        assert result["clean_name"] == "Room A"

    def test_clean_name_strips_event_prefix_noise(self, parser):
        result = parser._parse_with_regex("EVENT))1번방", "")
        assert result["clean_name"] == "1번방"

    def test_name_with_max_people_label(self, parser):
        result = parser._parse_with_regex("브라더 1번방 (최대인원 10명)", "")
        assert result["clean_name"] == "브라더 1번방"
        assert result["max_capacity"] == 10

    def test_clean_name_parenthetical_capacity_suffix_does_not_leave_dangling_paren(self, parser):
        result = parser._parse_with_regex("[개강특가] C룸(그랜드피아노 보유/최대 20명)", "")
        assert result["clean_name"] == "C룸"
        assert result["max_capacity"] == 20


class TestRuleBasedParsing:
    @pytest.fixture
    def parser(self):
        return RoomParserService()

    @pytest.mark.asyncio
    async def test_keyword_map_not_triggered_by_alphabet(self, parser):
        result = await parser.parse_room_desc("S룸", "최대 20인")
        assert result["max_capacity"] == 20

    @pytest.mark.asyncio
    async def test_batch_parsing(self, parser):
        result = await parser.parse_room_desc_batch(
            [
                {"id": "r1", "name": "[평일] A룸", "desc": "최대 6인"},
                {"id": "r2", "name": "B룸", "desc": "4~6인 권장"},
            ]
        )
        assert result["r1"]["day_type"] == "weekday"
        assert result["r1"]["max_capacity"] == 6
        assert result["r2"]["recommend_capacity_range"] == [4, 6]


class TestExportUnresolved:
    @pytest.fixture
    def service(self):
        with patch("app.services.room_collection_service.NaverMapCrawler"), \
             patch("app.services.room_collection_service.NaverRoomFetcher"), \
             patch("app.services.room_collection_service.RoomParserService"), \
             patch("app.services.room_collection_service.get_supabase_client"):
            return RoomCollectionService()

    @pytest.mark.asyncio
    async def test_exports_when_no_capacity(self, service, tmp_path, monkeypatch):
        import app.services.room_collection_service as mod

        fake_file = str(tmp_path / "app" / "services" / "room_collection_service.py")
        monkeypatch.setattr(mod, "__file__", fake_file)

        business = {"businessId": "b1", "businessDisplayName": "테스트합주실"}
        rooms = [{"bizItemId": "r1", "name": "룸A", "desc": "설명 없음"}]
        parsed_results = {"r1": {"max_capacity": None, "clean_name": "룸A"}}

        await service._export_unresolved(business, rooms, parsed_results)

        export_dir = tmp_path / "scripts" / "unresolved"
        files = list(export_dir.glob("unresolved_*.json"))
        assert len(files) == 1

        with open(files[0], "r", encoding="utf-8") as f:
            data = json.load(f)

        assert len(data) == 1
        assert data[0]["biz_item_id"] == "r1"
        assert data[0]["failure_reason"] == "no_capacity_info"

    @pytest.mark.asyncio
    async def test_no_export_when_capacity_found(self, service, tmp_path, monkeypatch):
        import app.services.room_collection_service as mod

        fake_file = str(tmp_path / "app" / "services" / "room_collection_service.py")
        monkeypatch.setattr(mod, "__file__", fake_file)

        business = {"businessId": "b1", "businessDisplayName": "테스트합주실"}
        rooms = [{"bizItemId": "r1", "name": "룸A", "desc": "최대 10인"}]
        parsed_results = {"r1": {"max_capacity": 10, "clean_name": "룸A"}}

        await service._export_unresolved(business, rooms, parsed_results)

        export_dir = tmp_path / "scripts" / "unresolved"
        if export_dir.exists():
            files = list(export_dir.glob("unresolved_*.json"))
            assert len(files) == 0

    @pytest.mark.asyncio
    async def test_export_uses_fallback_business_keys_when_primary_keys_missing(
        self, service, tmp_path, monkeypatch
    ):
        import app.services.room_collection_service as mod

        fake_file = str(tmp_path / "app" / "services" / "room_collection_service.py")
        monkeypatch.setattr(mod, "__file__", fake_file)

        business = {"id": "legacy-biz-1", "name": "Legacy Studio"}
        rooms = [{"bizItemId": "r1", "name": "Room A", "desc": "정보 없음"}]
        parsed_results = {"r1": {"max_capacity": None}}

        await service._export_unresolved(business, rooms, parsed_results)

        export_dir = tmp_path / "scripts" / "unresolved"
        files = list(export_dir.glob("unresolved_*.json"))
        assert len(files) == 1

        with open(files[0], "r", encoding="utf-8") as f:
            data = json.load(f)

        assert len(data) == 1
        assert data[0]["business_id"] == "legacy-biz-1"
        assert data[0]["business_name"] == "Legacy Studio"
