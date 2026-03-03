import pytest

from app.services.room_parser_service import RoomParserService


@pytest.mark.asyncio
async def test_batch_parser_returns_regex_results_for_each_room():
    parser = RoomParserService()

    result = await parser.parse_room_desc_batch(
        [
            {
                "id": "room-1",
                "name": "[평일] Room A",
                "desc": "최대 6인",
                "business_desc": "This context is ignored in rule-based parser",
            },
            {
                "id": "room-2",
                "name": "Room B",
                "desc": "4~6인 권장",
            },
        ]
    )

    assert set(result.keys()) == {"room-1", "room-2"}
    assert result["room-1"]["day_type"] == "weekday"
    assert result["room-1"]["max_capacity"] == 6
    assert result["room-2"]["recommend_capacity_range"] == [4, 6]
