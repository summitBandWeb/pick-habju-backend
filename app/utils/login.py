import httpx
from app.core.config import LOGIN_ID, LOGIN_PW, GROOVE_LOGIN_URL
from app.exception.crawler.groove_exception import GrooveCredentialError, GrooveLoginError


class LoginManager:
    """로그인 전담 매니저"""
    @staticmethod
    async def login(client: httpx.AsyncClient):
        """Groove 합주실 시스템에 로그인하여 세션을 획득한다.

        환경변수에서 로그인 URL과 자격 증명을 읽어 POST 요청을 전송하며,
        응답이 2xx가 아니면 예외를 발생시킨다.

        Args:
            client: 로그인 요청에 사용할 httpx.AsyncClient 인스턴스.

        Raises:
            GrooveCredentialError: 환경변수(GROOVE_BASE_URL, LOGIN_ID, LOGIN_PW)가 설정되지 않은 경우.
            GrooveLoginError: 로그인 HTTP 응답 상태 코드가 2xx 범위 밖인 경우.
        """
        if not GROOVE_LOGIN_URL:
            raise GrooveCredentialError("환경변수 GROOVE_BASE_URL 설정 필요")
        if not LOGIN_ID or not LOGIN_PW:
            raise GrooveCredentialError("환경변수 LOGIN_ID/LOGIN_PW 설정 필요")
        url = GROOVE_LOGIN_URL
        response = await client.post(
            url,
            data={"login_id": LOGIN_ID, "login_pw": LOGIN_PW},
            headers={
                "Referer": f"{GROOVE_LOGIN_URL}",
                "Content-Type": "application/x-www-form-urlencoded"
            }
        )
        if response.status_code < 200 or response.status_code >= 300:
            raise GrooveLoginError(
                f"Login failed with status code {response.status_code}"
            )
