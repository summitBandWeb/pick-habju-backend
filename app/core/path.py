# app/core/paths.py
from importlib.resources import files
from pathlib import Path

# app/data 내부 정적 파일 접근
def pkg_data_path(rel: str) -> Path:
    return files("app.data") / rel
