import pytest
from app.crawler.dream_checker import DreamCrawler

# 테스트용 크롤러 인스턴스 생성
crawler = DreamCrawler()

def test_parse_available_slot():
    """active 클래스가 있는 경우 예약 가능으로 판단되는지 테스트"""
    mock_html = """
    <div>
        <label title="2024-05-20 14시00분 (월)" class="time active">14:00</label>
        <label title="2024-05-20 15시00분 (월)" class="time">15:00</label>
    </div>
    """
    hour_slots = ["14:00", "15:00"]

    result = crawler._parse_html_content(mock_html, hour_slots)

    assert result["14:00"] is True
    assert result["15:00"] is False

def test_parse_unavailable_slot():
    """active 클래스가 없는 경우 예약 불가능으로 판단되는지 테스트"""
    mock_html = '<label title="2024-05-20 14시00분 (월)" class="time">14:00</label>'
    hour_slots = ["14:00"]

    result = crawler._parse_html_content(mock_html, hour_slots)

    assert result["14:00"] is False

def test_parse_missing_label():
    """해당 시간대의 label이 없으면 False 반환하는지 테스트"""
    mock_html = '<label title="2024-05-20 18시00분 (월)" class="time active">18:00</label>'
    hour_slots = ["14:00"] # 14시 라벨 없음

    result = crawler._parse_html_content(mock_html, hour_slots)

    assert result["14:00"] is False

def test_parse_broken_html():
    """깨진 HTML에서도 lxml이 최선으로 파싱하여 동작하는지 확인"""
    # 닫는 태그 누락 등
    mock_html = '<label title="2024-05-20 14시00분 (월)" class="time active">14:00'
    hour_slots = ["14:00"]

    result = crawler._parse_html_content(mock_html, hour_slots)

    assert result["14:00"] is True
