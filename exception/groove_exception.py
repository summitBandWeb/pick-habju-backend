class GrooveLoginError(Exception):
    """로그인 실패시 발생"""
    pass

class GrooveCredentialError(Exception):
    """환경변수 미설정 등 자격증명 오류"""
    pass