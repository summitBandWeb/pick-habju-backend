import json
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

LOGIN_ID = os.getenv("LOGIN_ID")
LOGIN_PW = os.getenv("LOGIN_PW")

GROOVE_BASE_URL = os.getenv("GROOVE_BASE_URL")
DREAM_BASE_URL = os.getenv("DREAM_BASE_URL")

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
