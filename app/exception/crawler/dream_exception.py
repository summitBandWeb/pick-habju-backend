from app.exception.base_exception import BaseCustomException, ErrorCode

class DreamRequestError(BaseCustomException):
    """드림 합주실 서버에 대한 네트워크 요청 실패 시 발생하는 예외"""
    def __init__(self, message: str = "드림 합주실 서버에 요청하는 중 오류가 발생했습니다."):
        super().__init__(
            message=message,
            error_code=ErrorCode.CRAWLER_EXECUTION_FAILED,
            status_code=503
        )

class DreamAvailabilityError(BaseCustomException):
    """드림 합주실의 응답을 파싱하거나 처리하는 중 발생하는 모든 예외"""
    def __init__(self, message: str = "드림 합주실의 예약 정보를 처리하는 중 오류가 발생했습니다."):
        super().__init__(
            message=message,
            error_code=ErrorCode.CRAWLER_PARSING_FAILED,
            status_code=500
        )
