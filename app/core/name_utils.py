import re
from typing import Any

def normalize_name_token(value: Any) -> str:
    """공백 제거, 대소문자 무시, 괄호 등 특수문자 제거 후 정규화된 문자열 반환"""
    if not isinstance(value, str):
        return ""
    cleaned = re.sub(r"\s+", " ", value).strip()
    if not cleaned:
        return ""
    return re.sub(r"[\s\-\_\(\)\[\]\{\}]+", "", cleaned).lower()
