import pytest
from app.validate.date_validator import validate_date_format, validate_date_not_past
from app.exception.common.date_exception import InvalidDateFormatError, PastDateNotAllowedError
from datetime import datetime, timedelta

def test_validate_date_valid():
    """오늘 날짜(YYYY-MM-DD 형식)는 유효한 날짜로 통과해야 한다."""
    today = datetime.now().strftime("%Y-%m-%d")
    # 정상 케이스
    validate_date_format(today)

def test_validate_date_invalid_format():
    """
    'YYYY/MM/DD' 형식은 잘못된 날짜형식으로 간주되어 InvalidDateFormatError 예외를 발생시켜야 한다.
    """
    tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y/%m/%d")  # 슬래시(/)로 일부러 잘못된 형식
    with pytest.raises(InvalidDateFormatError):
        validate_date_format(tomorrow)

def test_validate_date_past():
    """과거 날짜는 선택할 수 없으며 PastDateNotAllowedError 예외가 발생해야 한다."""
    yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    with pytest.raises(PastDateNotAllowedError):
        validate_date_not_past(yesterday)  # 과거 날짜
