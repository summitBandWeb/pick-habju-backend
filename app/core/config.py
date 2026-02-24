import os
import logging
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

APP_ENV = os.getenv("APP_ENV", "production")
IS_DEBUG = APP_ENV == "development"

LOGIN_ID = os.getenv("LOGIN_ID")
LOGIN_PW = os.getenv("LOGIN_PW")

GROOVE_BASE_URL = os.getenv("GROOVE_BASE_URL")
DREAM_BASE_URL = os.getenv("DREAM_BASE_URL")

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

# --- 필수 환경변수 검증 (URL 파생 변수 생성 이전에 수행) ---

if not SUPABASE_URL or not SUPABASE_KEY:
    raise ValueError("SUPABASE_URL과 SUPABASE_KEY 환경변수가 필요합니다.")

# NOTE: config.py는 setup_logging() 이전에 임포트되므로,
# 이 시점에서 logger.warning()을 호출하면 Python 기본 lastResort 핸들러로 출력됨.
# 따라서 누락 변수 리스트만 저장하고, 경고 출력은 setup_logging() 이후에 호출하도록 지연 처리.
_MISSING_CRAWLER_VARS: list[str] = []
if not GROOVE_BASE_URL:
    _MISSING_CRAWLER_VARS.append("GROOVE_BASE_URL")
if not DREAM_BASE_URL:
    _MISSING_CRAWLER_VARS.append("DREAM_BASE_URL")
if not LOGIN_ID:
    _MISSING_CRAWLER_VARS.append("LOGIN_ID")
if not LOGIN_PW:
    _MISSING_CRAWLER_VARS.append("LOGIN_PW")


def emit_startup_warnings() -> None:
    """setup_logging() 이후에 호출하여 정규 로그 포맷으로 환경변수 누락 경고를 출력합니다.

    Rationale:
        config.py는 모듈 임포트 시 즉시 실행되므로, 로깅 설정(핸들러, 포맷터)이
        완료되기 전에 logger.warning()을 호출하면 Python 기본 포맷으로 출력됩니다.
        이를 방지하기 위해 누락 정보를 저장해두었다가 setup_logging() 직후에
        본 함수를 호출하여 JSON 포맷 등 정규 로깅 파이프라인을 통해 경고합니다.
    """
    if _MISSING_CRAWLER_VARS:
        logger.warning(
            "필수 크롤러 환경변수가 누락되었습니다: %s. "
            "환경변수 누락 시 크롤링 기능이 비정상적으로 빈 결과를 반환할 수 있습니다.",
            ", ".join(_MISSING_CRAWLER_VARS)
        )

# --- URL 파생 변수 (None 안전 처리) ---
# NOTE: BASE_URL이 None이면 깨진 URL("None/...")이 생성되는 것을 방지하기 위해
# 조건부로 생성하며, None인 경우 크롤러 호출 시점에서 별도 예외 처리됨.

GROOVE_LOGIN_URL = f"{GROOVE_BASE_URL}/member/login_exec.asp" if GROOVE_BASE_URL else None
GROOVE_RESERVE_URL = f"{GROOVE_BASE_URL}/reservation/reserve_table_view.asp" if GROOVE_BASE_URL else None
GROOVE_RESERVE_URL1 = f"{GROOVE_BASE_URL}/reservation/reserve.asp" if GROOVE_BASE_URL else None

DREAM_LOGIN_URL = f"{DREAM_BASE_URL}/bbs/login_check.php" if DREAM_BASE_URL else None  # 드림 합주실 실제 로그인 URL
DREAM_HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Content-Type": "application/x-www-form-urlencoded",
}

CORS_ORIGIN_REGEX = os.getenv("CORS_ORIGIN_REGEX")


SUPABASE_TABLE = os.getenv("SUPABASE_TABLE", "v_full_info")

RATE_LIMIT_PER_MINUTE = int(os.getenv("RATE_LIMIT_PER_MINUTE", "5"))


# CORS 허용 오리진 (환경변수 기반)
def _parse_origins(value: str | None) -> list[str]:
    if not value:
        return []
    normalized = value.replace("\n", ",").replace(";", ",")
    items = [item.strip() for item in normalized.split(",")]
    return [item for item in items if item]


_DEFAULT_ALLOWED_ORIGINS = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "https://www.pickhabju.com",
    "https://pickhabju.com",
    "https://www.dev-pickhabju.store",
]

# 우선순위: CORS_ALLOWED_ORIGINS(복수) > FRONTEND_ORIGINS(복수) > FRONTEND_URL(단일)
_cors_allowed_origins = _parse_origins(os.getenv("CORS_ALLOWED_ORIGINS"))
_frontend_origins = _parse_origins(os.getenv("FRONTEND_ORIGINS"))
_single_frontend_url = [os.getenv("FRONTEND_URL")] if os.getenv("FRONTEND_URL") else []

# 중복 제거를 위해 dict 키 보존 방식 사용
ALLOWED_ORIGINS = list(
    dict.fromkeys(
        _DEFAULT_ALLOWED_ORIGINS
        + _cors_allowed_origins
        + _frontend_origins
        + _single_frontend_url
    )
)
