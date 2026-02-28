from app.models.dto import RoomDetail


def _room_payload(**overrides):
    payload = {
        "name": "테스트룸",
        "branch": None,
        "business_id": "biz-1",
        "biz_item_id": "room-1",
        "image_urls": None,
        "max_capacity": 8,
        "recommend_capacity_range": [4, 6],
        "price_config": None,
        "price_per_hour": 15000,
        "can_reserve_one_hour": True,
        # [이슈 1] Python 필드명: requiresContactOnSameDay (alias는 DB 컬럼명 requires_call_on_sameday 유지)
        "requires_call_on_sameday": False,
    }
    payload.update(overrides)
    return payload


def test_room_detail_branch_fallback_and_price_config_default():
    room = RoomDetail.model_validate(_room_payload())
    assert room.branch == "지점 정보 없음"
    assert room.priceConfig == {"default": 15000, "overrides": []}


def test_room_detail_capacity_flag_should_be_sanitized():
    """수동검토 플래그(100)가 들어오면 0/None으로 정제되는지 검증"""
    room = RoomDetail.model_validate(
        _room_payload(
            max_capacity=100,
            recommend_capacity_range=[100, 100],
        )
    )
    assert room.maxCapacity == 0
    # [이슈 6] recommendCapacityRange [100,100]은 MANUAL_REVIEW_FLAG로 None으로 정제됨
    assert room.recommendCapacityRange is None


def test_room_detail_recommend_capacity_range_preserved():
    """recommend_capacity_range가 정상 파싱되어 노출되는지 검증"""
    room = RoomDetail.model_validate(_room_payload(recommend_capacity_range=[3, 6]))
    assert room.recommendCapacityRange == [3, 6]

