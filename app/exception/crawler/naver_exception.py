from app.exception.base_exception import BaseCustomException, ErrorCode

class NaverRequestError(BaseCustomException):
    """네이버 예약 API에 대한 네트워크 요청 실패 시 발생하는 예외"""
    def __init__(self, message: str = "네이버 예약 API에 요청하는 중 오류가 발생했습니다."):
        super().__init__(
            message=message,
            error_code=ErrorCode.CRAWLER_EXECUTION_FAILED,
            status_code=503
        )

class NaverAvailabilityError(BaseCustomException):
    """네이버 예약 API 응답을 파싱하거나 처리하는 중 발생하는 모든 예외"""
    def __init__(self, message: str = "네이버 예약 정보를 처리하는 중 오류가 발생했습니다."):
        super().__init__(
            message=message,
            error_code=ErrorCode.CRAWLER_PARSING_FAILED,
            status_code=500
        )
