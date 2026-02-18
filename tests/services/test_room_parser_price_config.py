from app.services.room_parser_service import RoomParserService


def test_parse_with_regex_extracts_price_config_time_override():
    parser = RoomParserService()
    result = parser._parse_with_regex("테스트룸", "평일 18시 이후 15000원")
    price_config = result["price_config"]

    assert price_config is not None
    assert price_config["overrides"][0]["day_type"] == "weekday"
    assert price_config["overrides"][0]["start_hour"] == "18:00"
    assert price_config["overrides"][0]["price"] == 15000


def test_parse_with_regex_extracts_price_config_weekend_surcharge():
    parser = RoomParserService()
    result = parser._parse_with_regex("테스트룸", "주말 2000원 추가")
    price_config = result["price_config"]

    assert price_config is not None
    assert price_config["surcharges"][0]["day_type"] == "weekend"
    assert price_config["surcharges"][0]["amount"] == 2000
