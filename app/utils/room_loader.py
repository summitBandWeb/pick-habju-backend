import json
from pathlib import Path
import logging

ROOMS_FILE = Path(__file__).resolve().parent.parent / "data/rooms.json"
logger = logging.getLogger("app")

def load_rooms():
    try:
        with open(ROOMS_FILE, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        logger.error(
            "rooms.json not found",
            extra={"status": 500, "errorCode": "Common-002"}
        )
        raise
    except json.JSONDecodeError:
        logger.error(
            "rooms.json decode error",
            extra={"status": 500, "errorCode": "Common-002"}
        )
        raise
    except PermissionError:
        logger.error(
            "rooms.json permission denied",
            extra={"status": 500, "errorCode": "Common-002"}
        )
        raise
    except OSError:
        logger.error(
            "rooms.json IO error",
            extra={"status": 500, "errorCode": "Common-002"}
        )
        raise
