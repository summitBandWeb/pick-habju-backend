# app/core/paths.py
from importlib.resources import files
from pathlib import Path

# app/data 내부 정적 파일 접근
def pkg_data_path(rel: str) -> Path:
    """app.data 패키지 내부의 정적 파일 경로를 반환한다.

    Args:
        rel: app.data 기준 상대 파일 경로.

    Returns:
        해당 파일의 절대 Path 객체.
    """
    return files("app.data") / rel
