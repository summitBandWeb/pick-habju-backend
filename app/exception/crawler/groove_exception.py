class GrooveLoginError(Exception):
    """로그인 실패시 발생"""
    error_code = "Login-001"
    message = "로그인 중 문제가 발생했습니다. GROOVE 서버 오류!"
    status_code = 500

class GrooveCredentialError(Exception):
    """ENV 환경변수 미설정 등 자격증명 오류"""
    error_code = "Login-002"
    message = "로그인 중 내부 키 환경 설정 문제가 생겼습니다. Login, Password"
    status_code = 401
