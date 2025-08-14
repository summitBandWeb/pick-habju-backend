from app.exception.base_exception import BaseCustomException


class GrooveLoginError(BaseCustomException):
    """로그인 실패시 발생"""
    error_code = "Login-001"
    message = "로그인 중 문제가 발생했습니다. GROOVE 서버 오류!"
    status_code = 500

class GrooveCredentialError(BaseCustomException):
    """ENV 환경변수 미설정 등 자격증명 오류"""
    error_code = "Login-002"
    message = "로그인 중 내부 키 환경 설정 문제가 생겼습니다. Login, Password"
    status_code = 401

class GrooveRequestError(BaseCustomException):
    """그루브 서버 요청 실패 시 발생하는 예외"""
    error_code = "Groove-001"
    message = "그루브 서버에 요청하는 중 오류가 발생했습니다."
    status_code = 503 # Service Unavailable

class GrooveRoomParseError(BaseCustomException):
    """특정 방의 HTML 구조를 파싱할 수 없을 때 발생하는 예외"""
    error_code = "Groove-002"
    message = "방 정보를 파싱하는 중 오류가 발생했습니다."
    status_code = 500