import httpx
from app.core.config import GROOVE_BASE_URL, LOGIN_ID, LOGIN_PW, GROOVE_LOGIN_URL


class LoginManager:
    """로그인 전담 매니저"""
    @staticmethod
    async def login(client: httpx.AsyncClient):
        if not LOGIN_ID or not LOGIN_PW:
            raise ValueError("환경변수 LOGIN_ID/LOGIN_PW 설정 필요")
        url = f"{GROOVE_BASE_URL}/member/login_exec.asp"
        response = await client.post(
            url,
            data={"login_id": LOGIN_ID, "login_pw": LOGIN_PW},
            headers={
                "Referer": f"{GROOVE_LOGIN_URL}",
                "Content-Type": "application/x-www-form-urlencoded"
            }
        )
        if response.status_code < 200 or response.status_code >= 300:
            raise httpx.HTTPStatusError(
                f"Login failed with status code {response.status_code}",
                request=response.request,
                response=response
            )