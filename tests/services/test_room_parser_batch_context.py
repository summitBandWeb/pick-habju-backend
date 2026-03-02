from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.room_parser_service import RoomParserService


@pytest.mark.asyncio
async def test_batch_prompt_includes_business_context():
    mock_client = MagicMock()
    mock_client.generate = AsyncMock(return_value=None)
    parser = RoomParserService(ollama_client=mock_client)

    await parser.parse_room_desc_batch(
        [
            {
                "id": "room-1",
                "name": "Room A",
                "desc": "Max 6",
                "business_desc": "Store-wide context for equipment and rules",
            }
        ]
    )

    prompt = mock_client.generate.await_args.args[0]
    assert "Business Context" in prompt
    assert "Store-wide context for equipment and rules" in prompt
