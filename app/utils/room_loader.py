import json
import logging
from app.core.paths import pkg_data_path

logger = logging.getLogger("app")

def load_rooms():
    rooms_file = pkg_data_path("rooms.json")
    try:
        with rooms_file.open(encoding="utf-8") as f:
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
