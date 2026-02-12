import logging
import json
import os
import re
import stat
from logging.handlers import TimedRotatingFileHandler
from typing import Any
from app.core.context import get_trace_id


class LogMasker:
    """민감 정보를 마스킹하는 유틸리티 클래스"""
    # 1. 일반 변수/JSON 키: 공백이나 구분자(&, ,)로 값이 끝남
    # 1. 일반 변수/JSON 키: 공백이나 구분자(&, ,)로 값이 끝남
    SENSITIVE_KEYS: set[str] = {
        # Credentials - Basic
        "password", "passwd", "pwd", "pass",
        "secret", "secret_key", "client_secret",
        "key", "api_key", "apikey", "private_key", "public_key", "supabase_key",
        
        # Credentials - Token & Auth
        "token", "access_token", "refresh_token", "id_token", "bearer",
        "authorization", "auth", "x-api-key",
        "cookie", "session", "session_id", "sessionid",

        # Device & Identity
        "device_id", "x-device-id",
        
        # PII (Personal Identifiable Information)
        "user_id", "email", "phone", "mobile", "address",
        "ssn", "resident_number",
        "credit_card", "card_number", "cvc", "cvv", "account_number",
        
        # Infrastructure
        "database_url", "db_password", "connection_string"
    }

    # 2. 헤더류: 값이 공백을 포함할 수 있으며, 세미콜론(;)이나 줄바꿈으로 끝남
    SENSITIVE_HEADERS: set[str] = {
        "authorization", "cookie", "x-auth-token", "set-cookie"
    }
    
    # 통합 체크용 (dict 마스킹 시 사용)
    ALL_SENSITIVE = SENSITIVE_KEYS | SENSITIVE_HEADERS

    @classmethod
    def mask_dict(cls, data: Any) -> Any:
        if isinstance(data, dict):
            return {
                k: ("***" if k.lower() in cls.ALL_SENSITIVE else cls.mask_dict(v))
                for k, v in data.items()
            }
        elif isinstance(data, list):
            return [cls.mask_dict(i) for i in data]
        return data

    @classmethod
    def mask_string(cls, text: str) -> str:
        if not isinstance(text, str):
            return text
        
        # SENSITIVE_KEYS 패턴 미리 컴파일 (성능 최적화)
        keys_pattern = '|'.join(re.escape(k) for k in cls.SENSITIVE_KEYS)

        # 1차: 헤더 마스킹 (값에 공백 포함 가능, ; 또는 줄바꿈 등으로 종료)
        # 패턴: (헤더명)[:] (값...) -> 헤더는 보통 콜론(:) 사용
        header_pattern = r'({})\s*:\s*(?P<value>[^;\n]+)'.format(
            '|'.join(re.escape(k) for k in cls.SENSITIVE_HEADERS)
        )
        text = re.sub(header_pattern, r'\1: ***', text, flags=re.IGNORECASE)

        # 2차: Quoted Value 패턴 (JSON, Key="Value" 등)
        # 키: 따옴표가 있거나 없을 수 있음
        # 구분자: [:=] (JSON은 :, 쿼리스트링은 =)
        # 값: 따옴표(" 또는 ')로 감싸져 있음. 내부의 이스케이프 문자(\") 처리
        # 정규식 설명:
        #   (["']?): 키 앞의 따옴표 (선택)
        #   ({keys}): 민감 키
        #   \2: 키 뒤의 따옴표 (앞과 매칭되어야 함 -> \2로 참조? 아니면 ["']? 로 유연하게?)
        #   \s*[:=]\s*: 구분자
        #   (?P<quote>["']): 값의 시작 따옴표 (캡처)
        #   (?P<value>(?:(?=(\\?))\6.)*?): 값 내용 (이스케이프 문자 처리 포함)
        #   (?P=quote): 값의 종료 따옴표 (시작 따옴표와 동일)
        
        # 간단한 버전 (이스케이프 처리는 복잡하므로 비탐욕적 매칭 사용)
        quoted_pattern = r'(["\']?)({keys})\1\s*[:=]\s*(?P<quote>["\'])(?P<value>.*?)(?P=quote)'.format(keys=keys_pattern)
        
        def replace_quoted(match):
            full_match = match.group(0)
            quote = match.group('quote')
            value = match.group('value')
            # 값 부분을 ***로 대체 (따옴표는 유지)
            return full_match.replace(f"{quote}{value}{quote}", f"{quote}***{quote}")

        text = re.sub(quoted_pattern, replace_quoted, text, flags=re.IGNORECASE)

        # 3차: Unquoted Value 패턴 (Query String, Form Data 등)
        # 키: 따옴표가 있거나 없을 수 있음
        # 값: 따옴표, 공백, 구분자(&, ;, ,)를 제외한 문자열
        unquoted_pattern = r'(["\']?)({keys})\1\s*[:=]\s*(?P<value>[^"\',\s;&]+)'.format(keys=keys_pattern)
        
        def replace_unquoted(match):
            full_match = match.group(0)
            value = match.group('value')
            return full_match.replace(value, "***")

        text = re.sub(unquoted_pattern, replace_unquoted, text, flags=re.IGNORECASE)

        return text


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

    # 파일 권한 설정 (소유자만 읽기/쓰기 가능 - 0600)
    # 보안상 로그 파일은 다른 사용자가 읽을 수 없어야 함
    log_file = os.path.join(log_dir, "app.log")
    if os.path.exists(log_file):
        os.chmod(log_file, stat.S_IRUSR | stat.S_IWUSR)
