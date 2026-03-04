from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture
def mock_supabase():
    """왜: 가격 추론 검증에서 외부 DB 의존성을 제거하고, 사용처: _save_to_db upsert payload를 메모리 mock으로 검사한다."""
    mock = MagicMock()

    mock_room_table = MagicMock()
    mock_room_table.upsert.return_value.execute.return_value = MagicMock()
    mock_room_table.select.return_value.eq.return_value.execute.return_value = MagicMock(data=[])

    mock_branch_table = MagicMock()
    mock_branch_table.upsert.return_value.execute.return_value = MagicMock()

    def table_dispatcher(name):
        """왜: 테스트에서 허용 테이블 접근을 강제해 오타/누락을 조기 탐지하고, 사용처: supabase.table(name) 분기 라우팅에 사용한다."""
        tables = {
            "room": mock_room_table,
            "branch": mock_branch_table,
        }
        if name not in tables:
            raise AssertionError(f"Unexpected table access in test: {name}")
        return tables[name]

    mock.table.side_effect = table_dispatcher
    mock._room_table = mock_room_table
    mock._branch_table = mock_branch_table
    return mock


@pytest.fixture
def service(mock_supabase):
    """왜: 실제 크롤러/파서를 띄우지 않고 순수 저장 로직만 확인하려고, 사용처: RoomCollectionService 테스트 인스턴스를 주입한다."""
    with patch("app.services.room_collection_service.NaverMapCrawler"), patch(
        "app.services.room_collection_service.NaverRoomFetcher"
    ), patch("app.services.room_collection_service.RoomParserService"), patch(
        "app.services.room_collection_service.get_supabase_client", return_value=mock_supabase
    ):
        from app.services.room_collection_service import RoomCollectionService

        svc = RoomCollectionService()
        svc.supabase = mock_supabase
        return svc


@pytest.mark.asyncio
async def test_price_inference_uses_resolved_business_id_when_business_id_key_missing(service, mock_supabase):
    """왜: businessId 누락 payload에서도 id 기반 추론이 깨지면 수집 품질이 흔들린다. 사용처: _save_to_db의 business_id 해석 후 가격 규칙 적용 결과를 검증한다."""
    business = {
        "id": "917236",
        "businessDisplayName": "Test",
        "coordinates": None,
    }
    rooms = [
        {
            "bizItemId": "room1",
            "name": "Classic",
            "bizItemResources": [],
            "minMaxPrice": {"minPrice": 20000},
        }
    ]
    parsed_results = {"room1": {"max_capacity": None, "recommend_capacity": None}}

    await service._save_to_db(business, rooms, parsed_results)

    upsert_call = mock_supabase._room_table.upsert.call_args_list[-1]
    room_data = upsert_call[0][0]
    assert room_data["max_capacity"] == 12
    assert room_data["recommend_capacity"] == 6
    assert room_data["recommend_capacity_range"] == [4, 6]
