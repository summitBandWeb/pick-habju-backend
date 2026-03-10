from app.exception.base_exception import BaseCustomException, ErrorCode

class FavoriteLimitExceededError(BaseCustomException):
    """즐겨찾기 추가 상한 초과 시 발생하는 예외."""

    def __init__(self, message: str = "즐겨찾기 추가 상한에 도달했습니다."):
        """에러 코드와 메시지를 초기화한다."""
        super().__init__(
            status_code=400,
            error_code=ErrorCode.COMMON_BAD_REQUEST,
            message=message
        )
