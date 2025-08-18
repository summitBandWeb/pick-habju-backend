import pytest
import json
from pathlib import Path

@pytest.fixture(scope="session")
def rooms_data():
    """
    테스트 세션이 시작될 때 rooms.json 파일을 한 번만 로드하여
    그 내용을 테스트 내내 제공하는 픽스처입니다.
    """
    try:
        # 이 경로는 실제 프로젝트 구조에 맞게 조정해야 합니다.
        # (예: tests 폴더가 프로젝트 루트에 있다면 아래 경로가 맞습니다.)
        path = Path(__file__).parent.parent / "app/data/rooms.json"
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        pytest.fail(f"테스트에 필요한 rooms.json 파일을 찾을 수 없습니다. 경로: {path}")

