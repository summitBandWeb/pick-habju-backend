from app.exception.base_exception import BaseCustomException, ErrorCode

class GrooveCredentialError(BaseCustomException):
    """그루브 로그인 자격 증명 실패 시 발생하는 예외"""
    def __init__(self, message: str = "그루브 환경 변수 정보(ID, PASSWORD)가 유효하지 않습니다."):
        super().__init__(
            message=message,
            error_code=ErrorCode.CRAWLER_AUTH_FAILED,
            status_code=401
        )

class GrooveLoginError(BaseCustomException):
    """그루브 로그인 페이지 로드 또는 처리 실패 시 발생하는 예외"""
    def __init__(self, message: str = "그루브 로그인에 실패했습니다."):
        super().__init__(
            message=message,
            error_code=ErrorCode.CRAWLER_AUTH_FAILED,
            status_code=500
        )

class GrooveRequestError(BaseCustomException):
    """그루브 서버에 대한 네트워크 요청 실패 시 발생하는 예외"""
    def __init__(self, message: str = "그루브 서버에 요청하는 중 오류가 발생했습니다."):
        super().__init__(
            message=message,
            error_code=ErrorCode.CRAWLER_EXECUTION_FAILED,
            status_code=503 # Service Unavailable
        )

class GrooveRoomParseError(BaseCustomException):
    """특정 방의 HTML 구조를 파싱할 수 없을 때 발생하는 예외"""
    def __init__(self, message: str = "그루브 예약 페이지에서 방 정보를 파싱하는 중 오류가 발생했습니다."):
        super().__init__(
            message=message,
            error_code=ErrorCode.CRAWLER_PARSING_FAILED,
            status_code=500
        )
