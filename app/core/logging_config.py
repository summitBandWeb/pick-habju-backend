import logging
import json
import os
from logging.handlers import TimedRotatingFileHandler


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        # 메시지가 dict면 그대로 기반으로 삼고, 아니면 기본 구조 생성
        base_message = record.msg if isinstance(record.msg, dict) else {
            "message": record.getMessage()
        }

        log = {
            "timestamp": self.formatTime(record, datefmt="%Y-%m-%dT%H:%M:%S"),
            "level": record.levelname,
            "logger": record.name,
            **base_message,
        }

        return json.dumps(log, ensure_ascii=False)


def setup_logging(log_dir: str = "logs"):
    os.makedirs(log_dir, exist_ok=True)

    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)

    json_formatter = JsonFormatter()

    # 콘솔 핸들러
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(json_formatter)
    root_logger.addHandler(console_handler)

    # 일자별 파일 로테이션 핸들러 (자정 기준, 7일 보관)
    file_handler = TimedRotatingFileHandler(
        filename=os.path.join(log_dir, "app.log"),
        when="midnight",
        backupCount=7,
        encoding="utf-8",
        utc=False,
    )
    file_handler.setFormatter(json_formatter)
    root_logger.addHandler(file_handler)
