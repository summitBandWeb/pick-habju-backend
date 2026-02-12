import logging
import json
import os
import re
from logging.handlers import TimedRotatingFileHandler
from typing import Any
from app.core.context import get_trace_id


class LogMasker:
    """민감 정보를 마스킹하는 유틸리티 클래스"""
    SENSITIVE_KEYS: set[str] = {
        "password", "passwd", "token", "access_token", "refresh_token",
        "secret", "key", "api_key", "supabase_key", "device_id", "x-device-id",
        "authorization", "cookie"
    }

    @classmethod
    def mask_dict(cls, data: Any) -> Any:
        if isinstance(data, dict):
            return {
                k: (cls.mask_dict(v) if k.lower() not in cls.SENSITIVE_KEYS else "***")
                for k, v in data.items()
            }
        elif isinstance(data, list):
            return [cls.mask_dict(i) for i in data]
        return data

    @classmethod
    def mask_string(cls, text: str) -> str:
        if not isinstance(text, str):
            return text
        pattern = r'({})\s*[=:]\s*([^\s,;]+)'.format('|'.join(re.escape(k) for k in cls.SENSITIVE_KEYS))
        return re.sub(pattern, r'\1=***', text, flags=re.IGNORECASE)


class SensitiveDataFilter(logging.Filter):
    """
    로그 메시지 및 추가 데이터에서 민감한 정보를 찾아 마스킹 처리합니다.
    
    Rationale:
        보안 규정 준수를 위해 SUPABASE_KEY, password, token 등 
        민감한 필드 값이 로그 파일이나 출력에 포함되는 것을 방지합니다.
    """
    
    def filter(self, record: logging.LogRecord) -> bool:
        # Trace ID 주입
        record.trace_id = get_trace_id()
        
        # 메시지 마스킹
        if isinstance(record.msg, dict):
            record.msg = LogMasker.mask_dict(record.msg)
        elif isinstance(record.msg, str):
            record.msg = LogMasker.mask_string(record.msg)
            
        return True


class JsonFormatter(logging.Formatter):
    # 표준 LogRecord 속성 리스트 (extra 데이터를 구분하기 위함)
    DEFAULT_ATTRS = {
        "name", "msg", "args", "levelname", "levelno", "pathname", "filename",
        "module", "exc_info", "exc_text", "stack_info", "lineno", "funcName",
        "created", "msecs", "relativeCreated", "thread", "threadName",
        "processName", "process", "trace_id"
    }

    def format(self, record: logging.LogRecord) -> str:
        # 메시지가 dict면 그대로 기반으로 삼고, 아니면 기본 구조 생성
        message_body = record.msg if isinstance(record.msg, dict) else {
            "message": record.getMessage()
        }

        log = {
            "timestamp": self.formatTime(record, datefmt="%Y-%m-%dT%H:%M:%S"),
            "level": record.levelname,
            "logger": record.name,
            "trace_id": getattr(record, "trace_id", None),
            **message_body,
        }
        
        # extra로 전달된 커스텀 속성들을 추출하여 병합
        extra_data = {
            k: v for k, v in record.__dict__.items()
            if k not in self.DEFAULT_ATTRS and not k.startswith("_")
        }
        
        if extra_data:
            # 런타임에 주입된 extra 데이터에 대해서도 마스킹 적용
            masked_extra = LogMasker.mask_dict(extra_data)
            log.update(masked_extra)
            
        return json.dumps(log, ensure_ascii=False)


def setup_logging(log_dir: str = "logs"):
    os.makedirs(log_dir, exist_ok=True)

    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)

    # 기존 핸들러 제거 (중복 방지)
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    json_formatter = JsonFormatter()
    sensitive_filter = SensitiveDataFilter()

    # 콘솔 핸들러
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(json_formatter)
    console_handler.addFilter(sensitive_filter)
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
    file_handler.addFilter(sensitive_filter)
    root_logger.addHandler(file_handler)
