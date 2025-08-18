from app.exception.base_exception import BaseCustomException

class DreamRequestError(BaseCustomException):
    """드림 합주실 서버에 대한 네트워크 요청 실패 시 발생하는 예외"""
    error_code = "Dream-001"
    message = "드림 합주실 서버에 요청하는 중 오류가 발생했습니다."
    status_code = 503

class DreamAvailabilityError(BaseCustomException):
    """드림 합주실의 응답을 파싱하거나 처리하는 중 발생하는 모든 예외"""
    error_code = "Dream-002"
    message = "드림 합주실의 예약 정보를 처리하는 중 오류가 발생했습니다."
    status_code = 500
