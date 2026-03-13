from unittest.mock import AsyncMock, patch

import pytest


@pytest.fixture
def service():
    with patch("app.services.room_collection_service.NaverMapCrawler"), patch(
        "app.services.room_collection_service.NaverRoomFetcher"
    ), patch("app.services.room_collection_service.RoomParserService"), patch(
        "app.services.room_collection_service.get_supabase_client"
    ):
        from app.services.room_collection_service import RoomCollectionService

        return RoomCollectionService()


# --- Hard 키워드 필터링 ---


def test_filter_rooms_excludes_hard_keyword_rooms(service):
    """Hard 키워드(레슨, 수업, 대여, 댄스 등)는 무조건 필터링된다."""
    rooms = [
        {"bizItemId": "room-ok", "name": "A Room", "minMaxPrice": {"minPrice": 15000}},
        {"bizItemId": "room-lesson", "name": "재즈피아노 레슨", "minMaxPrice": {"minPrice": 20000}},
        {"bizItemId": "room-class", "name": "드럼 수업 A", "minMaxPrice": {"minPrice": 18000}},
        {"bizItemId": "room-rental", "name": "기타 대여", "minMaxPrice": {"minPrice": 5000}},
        {"bizItemId": "room-dance", "name": "댄스 연습실", "minMaxPrice": {"minPrice": 10000}},
        {"bizItemId": "room-party", "name": "파티룸", "minMaxPrice": {"minPrice": 30000}},
    ]

    selected, stats = service._filter_rooms_for_regex_parsing(rooms)

    assert len(selected) == 1
    assert selected[0]["bizItemId"] == "room-ok"
    assert stats["non_rehearsal_keyword"] == 5


# --- Soft 키워드: Business 레벨 판정 ---


def test_soft_keyword_preserved_when_business_is_rehearsal(service):
    """Business가 합주실이면 Soft 키워드(레코딩, 녹음 등) 룸은 보존된다."""
    rooms = [
        {"bizItemId": "room-ok", "name": "A Room", "minMaxPrice": {"minPrice": 15000}},
        {"bizItemId": "room-recording", "name": "레코딩 스튜디오", "minMaxPrice": {"minPrice": 25000}},
    ]

    selected, stats = service._filter_rooms_for_regex_parsing(
        rooms, business_is_rehearsal=True,
    )

    assert len(selected) == 2
    assert stats["non_rehearsal_keyword"] == 0


def test_soft_keyword_filtered_when_business_is_not_rehearsal(service):
    """Business가 합주실이 아니면 Soft 키워드 룸은 필터링된다."""
    rooms = [
        {"bizItemId": "room-recording", "name": "레코딩 스튜디오", "minMaxPrice": {"minPrice": 25000}},
    ]

    selected, stats = service._filter_rooms_for_regex_parsing(
        rooms, business_is_rehearsal=False,
    )

    assert len(selected) == 0
    assert stats["non_rehearsal_keyword"] == 1


def test_soft_keyword_preserved_when_room_name_has_rehearsal_keyword(service):
    """룸 이름에 합주 키워드가 있으면 Soft 키워드여도 보존된다 (business 여부 무관)."""
    rooms = [
        {"bizItemId": "room-both", "name": "합주실 겸 레코딩", "minMaxPrice": {"minPrice": 20000}},
    ]

    selected, stats = service._filter_rooms_for_regex_parsing(
        rooms, business_is_rehearsal=False,
    )

    assert len(selected) == 1
    assert stats["non_rehearsal_keyword"] == 0


# --- MIN_REHEARSAL_PRICE ---


def test_filter_rooms_excludes_below_min_price(service):
    """MIN_REHEARSAL_PRICE(5000원) 미만 룸은 필터링된다."""
    rooms = [
        {"bizItemId": "room-cheap", "name": "저렴한 연습실", "minMaxPrice": {"minPrice": 3000}},
        {"bizItemId": "room-ok", "name": "A Room", "minMaxPrice": {"minPrice": 15000}},
        {"bizItemId": "room-boundary", "name": "B Room", "minMaxPrice": {"minPrice": 5000}},
    ]

    selected, stats = service._filter_rooms_for_regex_parsing(rooms)

    assert len(selected) == 2
    selected_ids = [r["bizItemId"] for r in selected]
    assert "room-cheap" not in selected_ids
    assert "room-ok" in selected_ids
    assert "room-boundary" in selected_ids
    assert stats["missing_reservation"] == 1


def test_min_rehearsal_price_constant_is_5000(service):
    """MIN_REHEARSAL_PRICE 상수가 5000인지 확인"""
    assert service.MIN_REHEARSAL_PRICE == 5000


# --- collect_by_id 통합 ---


@pytest.mark.asyncio
async def test_collect_by_id_skips_when_all_rooms_are_hard_keyword(service):
    """모든 룸이 Hard 키워드면 전체 스킵된다."""
    service.room_fetcher.fetch_full_info = AsyncMock(
        return_value={
            "business": {
                "businessId": "1574159",
                "businessDisplayName": "Brown Studio",
                "desc": "test",
                "coordinates": {"latitude": 37.0, "longitude": 127.0},
            },
            "rooms": [
                {"bizItemId": "r1", "name": "재즈화성학레슨", "minMaxPrice": {"minPrice": 18000}},
                {"bizItemId": "r2", "name": "드럼 수업 초급반", "minMaxPrice": {"minPrice": 22000}},
            ],
            "subway": None,
        }
    )
    service.parser_service.parse_room_desc_batch = AsyncMock(return_value={})
    service._save_to_db = AsyncMock()
    service._export_unresolved = AsyncMock()

    result = await service.collect_by_id("1574159")

    assert result["status"] == "skipped_all_rooms_filtered"
    assert result["reason"] == "rooms_filtered_non_rehearsal_keywords"
    assert result["non_rehearsal_keyword"] == 2
    service.parser_service.parse_room_desc_batch.assert_not_awaited()
    service._save_to_db.assert_not_awaited()
    service._export_unresolved.assert_not_awaited()
