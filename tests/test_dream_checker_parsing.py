import pytest
from app.crawler.dream_checker import DreamCrawler

# 테스트용 크롤러 인스턴스 생성
crawler = DreamCrawler()

# 실제 드림 API title 형식: "22시00분 ~ 23시00분  최대 15명 예약가능" (가능)
#                           "21시00분 ~ 22시00분 예약마감"            (마감)

def test_parse_available_slot():
    """active 클래스가 있는 경우 예약 가능으로 판단되는지 테스트"""
    mock_html = """
    <ul>
        <li><label class="btn-time active" title="14시00분 ~ 15시00분  최대 15명 예약가능">14:00 ~ 15:00</label></li>
        <li><label class="btn-time " title="15시00분 ~ 16시00분 예약마감">15:00 ~ 16:00 (예약마감)</label></li>
    </ul>
    """
    hour_slots = ["14:00", "15:00"]

    result = crawler._parse_html_content(mock_html, hour_slots)

    assert result["14:00"] is True
    assert result["15:00"] is False

def test_parse_unavailable_slot():
    """active 클래스가 없는 경우 예약 불가능으로 판단되는지 테스트"""
    mock_html = '<label class="btn-time " title="14시00분 ~ 15시00분 예약마감">14:00 ~ 15:00 (예약마감)</label>'
    hour_slots = ["14:00"]

    result = crawler._parse_html_content(mock_html, hour_slots)

    assert result["14:00"] is False

def test_parse_missing_label():
    """해당 시간대의 label이 없으면 False 반환하는지 테스트"""
    mock_html = '<label class="btn-time active" title="18시00분 ~ 19시00분  최대 15명 예약가능">18:00 ~ 19:00</label>'
    hour_slots = ["14:00"]  # 14시 라벨 없음

    result = crawler._parse_html_content(mock_html, hour_slots)

    assert result["14:00"] is False

def test_parse_broken_html():
    """깨진 HTML에서도 lxml이 최선으로 파싱하여 동작하는지 확인"""
    # 닫는 태그 누락 등
    mock_html = '<label class="btn-time active" title="14시00분 ~ 15시00분  최대 15명 예약가능">14:00'
    hour_slots = ["14:00"]

    result = crawler._parse_html_content(mock_html, hour_slots)

    assert result["14:00"] is True

def test_parse_end_time_not_matched_as_start():
    """이전 슬롯의 종료 시간이 다음 슬롯의 시작 시간으로 오인되지 않는지 테스트 (회귀)

    버그 재현 시나리오:
      - 21:00 슬롯: title="21시00분 ~ 22시00분 예약마감" (active 없음)
      - 22:00 슬롯: title="22시00분 ~ 23시00분  최대 15명 예약가능" (active 있음)

    `target_time in t` 검색 시, "22시00분"이 21:00 슬롯 title에도 포함되어
    첫 매칭이 21:00 슬롯(active 없음) → 잘못된 False 반환.
    `t.startswith(target_time)` 으로 수정 후 22:00 슬롯을 정확히 매칭해야 함.
    """
    mock_html = """
    <ul>
        <li><label class="btn-time " title="21시00분 ~ 22시00분 예약마감">21:00 ~ 22:00 (예약마감)</label></li>
        <li><label class="btn-time active" title="22시00분 ~ 23시00분  최대 15명 예약가능">22:00 ~ 23:00</label></li>
        <li><label class="btn-time active" title="23시00분 ~ 00시00분  최대 15명 예약가능">23:00 ~ 00:00</label></li>
    </ul>
    """
    hour_slots = ["22:00", "23:00"]

    result = crawler._parse_html_content(mock_html, hour_slots)

    assert result["22:00"] is True, "22:00은 active 슬롯이므로 True여야 함 (이전 슬롯 종료 시간에 오인 매칭 시 False)"
    assert result["23:00"] is True
