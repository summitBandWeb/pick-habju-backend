import httpx
from config import LOGIN_ID, LOGIN_PW, GROOVE_LOGIN_URL, DREAM_LOGIN_URL, DREAM_BASE_URL # config.py에 추가해야 할 설정들
from utils.auth.baseLoginHandler import BaseLoginHandler

class GrooveLoginHandler(BaseLoginHandler):
    def __init__(self):
        self.login_id = LOGIN_ID
        self.login_pw = LOGIN_PW
        self.login_url = GROOVE_LOGIN_URL
        self.login_headers = {
            "Referer": GROOVE_LOGIN_URL,
            "Content-Type": "application/x-www-form-urlencoded"
        }

    async def login(self, client: httpx.AsyncClient) -> httpx.AsyncClient:
        login_data = {
            "login_id": self.login_id,
            "login_pw": self.login_pw
        }
        try:
            login_res = await client.post(
                self.login_url,
                data=login_data,
                headers=self.login_headers
            )
            login_res.raise_for_status() # HTTP 오류가 발생하면 예외 발생
            return client
        except httpx.HTTPStatusError as e:
            print(f"HTTP 오류 발생 (그루브): {e.response.status_code}")
            raise # 로그인 실패 시 예외를 다시 발생시켜 상위 호출자에게 알림
        except Exception as e:
            print(f"예상치 못한 오류 (그루브): {e}")
            raise