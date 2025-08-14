import json
from pathlib import Path

ROOMS_FILE = Path(__file__).resolve().parent.parent.parent / "rooms.json"

def load_rooms():
    try:
        with open(ROOMS_FILE, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"[ERROR] 파일을 찾을 수 없습니다: {ROOMS_FILE}")
        raise
    except json.JSONDecodeError as e:
        print(f"[ERROR] JSON 형식 오류: {e}")
        raise
    except PermissionError:
        print(f"[ERROR] 파일에 접근할 권한이 없습니다: {ROOMS_FILE}")
        raise
    except OSError as e:
        print(f"[ERROR] 기타 파일 입출력 오류: {e}")
        raise
