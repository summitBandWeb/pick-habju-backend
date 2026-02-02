import re
from datetime import datetime, date as dt_date
from app.exception.common.date_exception import InvalidDateFormatError, PastDateNotAllowedError

DATE_PATTERN = r"^\d{4}-\d{2}-\d{2}$"

def validate_date_format(date: str):
    """날짜 형식(YYYY-MM-DD) 검증"""
    if not re.match(DATE_PATTERN, date):
        raise InvalidDateFormatError(f"날짜 형식이 잘못되었습니다: {date}")

def validate_date_not_past(date: str):
    """과거 날짜 여부 검증"""
    today = dt_date.today()
    input_date = datetime.strptime(date, "%Y-%m-%d").date()
    if input_date < today:
        raise PastDateNotAllowedError(f"과거 날짜는 허용되지 않습니다: {date}")

def validate_date(date: str):
    """날짜 전체 검증(형식 + 과거여부)"""
    validate_date_format(date)
    validate_date_not_past(date)
