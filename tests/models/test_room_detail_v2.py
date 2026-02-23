from app.models.dto import RoomDetail


def _room_payload(**overrides):
    payload = {
        "name": "테스트룸",
        "branch": None,
        "business_id": "biz-1",
        "biz_item_id": "room-1",
        "image_urls": None,
        "max_capacity": 8,
        "recommend_capacity": 6,
        "price_config": None,
        "price_per_hour": 15000,
        "can_reserve_one_hour": True,
        "requires_call_on_sameday": False,
    }
    payload.update(overrides)
    return payload


def test_room_detail_branch_fallback_and_price_config_default():
    room = RoomDetail.model_validate(_room_payload())
    assert room.branch == "지점 정보 없음"
    assert room.priceConfig == {"default": 15000, "overrides": []}


def test_room_detail_capacity_flag_should_be_sanitized():
    room = RoomDetail.model_validate(
        _room_payload(
            max_capacity=100,
            recommend_capacity=100,
            recommend_capacity_range=[100, 100],
        )
    )
    assert room.maxCapacity == 0
    assert room.recommendCapacity == 0
    assert room.recommendCapacityRange is None


def test_room_detail_legacy_recommend_capacity_range_upcast():
    room = RoomDetail.model_validate(_room_payload(recommend_capacity=6))
    assert room.recommendCapacityRange == [4, 6]
