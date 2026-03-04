import re
from typing import Any


def normalize_name_token(value: Any) -> str:
    """문자열 비교용 토큰으로 정규화한다.

    한글/영문/숫자를 제외한 문자를 제거하고 소문자로 통일한다.
    예: "안녕 하@ 세요# 반가워요" -> "안녕하세요반가워요"
    """
    if not isinstance(value, str):
        return ""
    # 지점명/룸명 비교 시 특수문자 차이(@, #, -, _, 괄호 등)로 인한 오탐을 줄이기 위한 정규화.
    cleaned = re.sub(r"[^0-9A-Za-z가-힣]+", "", value)
    if not cleaned:
        return ""
    return cleaned.lower()
