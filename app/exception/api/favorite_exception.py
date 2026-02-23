from app.exception.base_exception import BaseCustomException, ErrorCode

class FavoriteLimitExceededError(BaseCustomException):
    def __init__(self, message: str = "즐겨찾기 추가 상한에 도달했습니다."):
        super().__init__(
            status_code=400,
            error_code=ErrorCode.COMMON_BAD_REQUEST,
            message=message
        )
