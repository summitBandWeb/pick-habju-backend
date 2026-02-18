from app.models.dto import RoomDetail
from app.services.availability_service import AvailabilityService


def _room_detail(**overrides) -> RoomDetail:
    payload = {
        "name": "가격테스트룸",
        "branch": "테스트지점",
        "business_id": "biz-price",
        "biz_item_id": "room-price",
        "image_urls": [],
        "max_capacity": 6,
        "recommend_capacity": 4,
        "price_config": None,
        "price_per_hour": 10000,
        "can_reserve_one_hour": True,
        "requires_call_on_sameday": False,
    }
    payload.update(overrides)
    return RoomDetail.model_validate(payload)


def test_generate_time_slots_supports_24h():
    service = AvailabilityService(crawlers_map={})
    assert service.generate_time_slots("22:00", "24:00") == ["22:00", "23:00", "24:00"]


def test_calculate_total_price_with_fallback_default_price():
    service = AvailabilityService(crawlers_map={})
    room = _room_detail(price_per_hour=12000, price_config=None)
    total = service.calculate_total_price(room, "2026-02-20", ["18:00", "19:00"])
    assert total == 24000


def test_calculate_total_price_with_override_and_surcharge():
    service = AvailabilityService(crawlers_map={})
    room = _room_detail(
        price_per_hour=10000,
        price_config={
            "default": 10000,
            "overrides": [
                {
                    "day_type": "weekend",
                    "start_hour": "18:00",
                    "end_hour": "24:00",
                    "price": 15000,
                }
            ],
            "surcharges": [{"day_type": "weekend", "amount": 2000}],
        },
    )
    # 2026-02-22 is Sunday
    total = service.calculate_total_price(room, "2026-02-22", ["17:00", "18:00", "19:00"])
    # 17시: 10000+2000, 18/19시: 15000+2000 each
    assert total == 46000
