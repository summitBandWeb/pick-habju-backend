from app.exception.base_exception import BaseCustomException

class ResponseMismatchError(BaseCustomException):
    """요청한 방과 응답한 방의 biz_item_id가 일치하지 않을 때 발생"""
    error_code = "Response-001"
    message = "요청과 응답의 합주실 ID 리스트가 불일치합니다."
    status_code = 500
