import os
from dotenv import load_dotenv

load_dotenv()

APP_ENV = os.getenv("APP_ENV", "production")
IS_DEBUG = APP_ENV == "development"

LOGIN_ID = os.getenv("LOGIN_ID")
LOGIN_PW = os.getenv("LOGIN_PW")

GROOVE_BASE_URL = os.getenv("GROOVE_BASE_URL")
DREAM_BASE_URL = os.getenv("DREAM_BASE_URL")

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

GROOVE_LOGIN_URL = f"{GROOVE_BASE_URL}/member/login_exec.asp"
GROOVE_RESERVE_URL = f"{GROOVE_BASE_URL}/reservation/reserve_table_view.asp"
GROOVE_RESERVE_URL1 = f"{GROOVE_BASE_URL}/reservation/reserve.asp"

DREAM_LOGIN_URL = f"{DREAM_BASE_URL}/bbs/login_check.php" # 드림 합주실 실제 로그인 URL
DREAM_HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Content-Type": "application/x-www-form-urlencoded"
}
DREAM_COOKIES = {
    'PHPSESSID': 'your_dream_php_session_id',
    'e1192aefb64683cc97abb83c71057733': 'your_dream_cookie_value'
}

SUPABASE_TABLE = os.getenv("SUPABASE_TABLE", "v_full_info")

RATE_LIMIT_PER_MINUTE = int(os.getenv("RATE_LIMIT_PER_MINUTE", "5"))

if not SUPABASE_URL or not SUPABASE_KEY:
    raise ValueError("SUPABASE_URL과 SUPABASE_KEY 환경변수가 필요합니다.")

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
]

# 우선순위: CORS_ALLOWED_ORIGINS(복수) > FRONTEND_ORIGINS(복수) > FRONTEND_URL(단일)
_cors_allowed_origins = _parse_origins(os.getenv("CORS_ALLOWED_ORIGINS"))
_frontend_origins = _parse_origins(os.getenv("FRONTEND_ORIGINS"))
_single_frontend_url = [os.getenv("FRONTEND_URL")] if os.getenv("FRONTEND_URL") else []

# 중복 제거를 위해 dict 키 보존 방식 사용
ALLOWED_ORIGINS = list(dict.fromkeys(_DEFAULT_ALLOWED_ORIGINS + _cors_allowed_origins + _frontend_origins + _single_frontend_url))
