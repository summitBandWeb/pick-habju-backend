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

    # --- 클래스 로딩 시 한 번만 컴파일하는 정규식 패턴 ---
    # NOTE: 매 mask_string() 호출마다 패턴을 재생성하면 고부하 환경에서
    #       심각한 CPU 오버헤드 발생. 클래스 변수로 한 번만 컴파일.
    _KEYS_PATTERN = '|'.join(re.escape(k) for k in SENSITIVE_KEYS)

    _HEADER_RE = re.compile(
        r'({})\s*:\s*(?P<value>[^;\n]+)'.format(
            '|'.join(re.escape(k) for k in SENSITIVE_HEADERS)
        ),
        re.IGNORECASE
    )

    _QUOTED_RE = re.compile(
        r'(["\']?)({keys})\1\s*[:=]\s*(?P<quote>["\'])(?P<value>.*?)(?P=quote)'.format(
            keys=_KEYS_PATTERN
        ),
        re.IGNORECASE
    )

    _UNQUOTED_RE = re.compile(
        r'(["\']?)({keys})\1\s*[:=]\s*(?P<value>[^"\',\s;&]+)'.format(
            keys=_KEYS_PATTERN
        ),
        re.IGNORECASE
    )

    # PII 형식 패턴: 키워드 매칭으로 잡히지 않는 이메일/전화번호를 직접 탐지
    _EMAIL_RE = re.compile(
        r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b'
    )
    _PHONE_RE = re.compile(
        r'\b\d{2,3}-\d{3,4}-\d{4}\b'
    )

    @classmethod
    def mask_dict(cls, data: Any, depth: int = 0) -> Any:
        # 순환 참조 및 너무 깊은 중첩 방지 (최대 10단계)
        if depth > 10:
            return str(data)

        if isinstance(data, dict):
            return {
                k: ("***" if k.lower() in cls.ALL_SENSITIVE else cls.mask_dict(v, depth + 1))
                for k, v in data.items()
            }
        elif isinstance(data, list):
            return [cls.mask_dict(i, depth + 1) for i in data]
        return data

    @classmethod
    def mask_string(cls, text: str) -> str:
        """문자열 내 민감 정보를 마스킹합니다.

        Rationale:
            정규식 패턴은 클래스 로딩 시 한 번만 컴파일하여 CPU 오버헤드를 제거함.
            마스킹 순서: 1) 헤더 → 2) 따옴표 값 → 3) 비따옴표 값 → 4) 이메일 → 5) 전화번호
        """
        if not isinstance(text, str):
            return text
        
        # 1차: 헤더 마스킹 (값에 공백 포함 가능, ; 또는 줄바꿈 등으로 종료)
        text = cls._HEADER_RE.sub(r'\1: ***', text)

        # 2차: Quoted Value 패턴 (JSON, Key="Value" 등)
        text = cls._QUOTED_RE.sub(cls._replace_quoted, text)

        # 3차: Unquoted Value 패턴 (Query String, Form Data 등)
        text = cls._UNQUOTED_RE.sub(cls._replace_unquoted, text)

        # 4차: 이메일 형식 마스킹 (키워드 없이 노출된 이메일 주소 포착)
        text = cls._EMAIL_RE.sub('***@***.***', text)

        # 5차: 전화번호 형식 마스킹 (010-1234-5678 등)
        text = cls._PHONE_RE.sub('***-****-****', text)

        return text

    @staticmethod
    def _replace_quoted(match):
        """따옴표로 감싸진 민감 값을 ***로 대체 (따옴표 구조는 유지)"""
        full_match = match.group(0)
        quote = match.group('quote')
        value = match.group('value')
        return full_match.replace(f"{quote}{value}{quote}", f"{quote}***{quote}")

    @staticmethod
    def _replace_unquoted(match):
        """따옴표 없는 민감 값을 ***로 대체"""
        full_match = match.group(0)
        value = match.group('value')
        return full_match.replace(value, "***")


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

    # NOTE: 로테이션된 파일(app.log.2026-02-13)에도 0600 권한을 적용하기 위해
    #       doRollover를 오버라이드한 커스텀 핸들러 사용.
    #       기본 TimedRotatingFileHandler는 새 파일을 umask 기본값으로 생성함.
    class SecureRotatingFileHandler(TimedRotatingFileHandler):
        """로테이션 시 모든 로그 파일에 0600 권한을 자동 적용하는 핸들러"""

        def doRollover(self):
            super().doRollover()
            # 로테이션 후 현재 로그 파일 권한 설정
            if self.baseFilename and os.path.exists(self.baseFilename):
                os.chmod(self.baseFilename, stat.S_IRUSR | stat.S_IWUSR)
            # 백업 파일들에도 동일한 권한 적용
            for filename in os.listdir(log_dir):
                if filename.startswith("app.log"):
                    filepath = os.path.join(log_dir, filename)
                    os.chmod(filepath, stat.S_IRUSR | stat.S_IWUSR)

    # 일자별 파일 로테이션 핸들러 (자정 기준, 7일 보관)
    file_handler = SecureRotatingFileHandler(
        filename=os.path.join(log_dir, "app.log"),
        when="midnight",
        backupCount=7,
        encoding="utf-8",
        utc=False,
    )
    file_handler.setFormatter(json_formatter)
    file_handler.addFilter(sensitive_filter)
    root_logger.addHandler(file_handler)

    # 초기 파일 권한 설정 (소유자만 읽기/쓰기 가능 - 0600)
    log_file = os.path.join(log_dir, "app.log")
    if os.path.exists(log_file):
        os.chmod(log_file, stat.S_IRUSR | stat.S_IWUSR)

