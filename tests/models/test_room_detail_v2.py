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


def test_alias_choices_old_field_name():
    """구 DB 컬럼명(requires_call_on_sameday)으로도 파싱되는지 검증"""
    payload = _room_payload()
    payload.pop("requires_call_on_sameday", None)
    payload["requires_call_on_sameday"] = True
    room = RoomDetail.model_validate(payload)
    assert room.requiresContactOnSameDay is True


def test_alias_choices_new_field_name():
    """신 DB 컬럼명(requires_contact_on_sameday)으로도 파싱되는지 검증"""
    payload = _room_payload()
    payload.pop("requires_call_on_sameday", None)
    payload["requires_contact_on_sameday"] = True
    room = RoomDetail.model_validate(payload)
    assert room.requiresContactOnSameDay is True


def test_alias_choices_precedence():
    """우선순위(새 컬럼명 > 구 컬럼명) 검증"""
    payload = _room_payload()
    payload["requires_contact_on_sameday"] = False
    payload["requires_call_on_sameday"] = True
    room = RoomDetail.model_validate(payload)
    assert room.requiresContactOnSameDay is False


# ── #257 capacity range 이상값 방어 테스트 ─────────────────────────────────────

def test_recommend_capacity_range_sentinel_50_50_returns_none():
    """[50,50]: MANUAL_REVIEW_FLAG(100)이 50으로 clamp된 레거시 산물 → None으로 정제"""
    room = RoomDetail.model_validate(
        _room_payload(max_capacity=8, recommend_capacity_range=[50, 50])
    )
    assert room.recommendCapacityRange is None


def test_recommend_capacity_range_upper_exceeds_max_is_clamped():
    """range 상한이 max_capacity 초과 → max_capacity 기준으로 clamp"""
    room = RoomDetail.model_validate(
        _room_payload(max_capacity=8, recommend_capacity_range=[4, 12])
    )
    assert room.recommendCapacityRange == [4, 8]


def test_recommend_capacity_range_lower_zero_is_clamped_to_one():
    """range 하한이 0 → clamp 후 하한 최솟값 1 보장"""
    room = RoomDetail.model_validate(
        _room_payload(max_capacity=8, recommend_capacity_range=[0, 12])
    )
    assert room.recommendCapacityRange == [1, 8]


def test_recommend_capacity_range_not_clamped_when_max_is_flag():
    """maxCapacity=100(MANUAL_REVIEW_FLAG)일 때 range clamp가 FLAG값(100) 기준으로 동작하면 안 됨"""
    room = RoomDetail.model_validate(
        _room_payload(max_capacity=100, recommend_capacity_range=[3, 150])
    )
    assert room.maxCapacity == 0
    # maxCapacity=0이므로 clamp 조건(> 0) 미충족 → range는 그대로 유지
    assert room.recommendCapacityRange == [3, 150]

