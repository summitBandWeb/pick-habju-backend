from app.exception.base_exception import BaseCustomException, ErrorCode


class FavoriteLimitExceededError(BaseCustomException):
    def __init__(self, message: str = "즐겨찾기 추가 상한을 초과했습니다."):
        super().__init__(
            status_code=400,
            error_code=ErrorCode.COMMON_BAD_REQUEST,
            message=message,
        )


class FavoriteRepositoryUnavailableError(BaseCustomException):
    """왜: 즐겨찾기 저장소 장애를 빈 결과로 은닉하지 않고 API 레이어에 명시적으로 전파하기 위함.
    사용처: SupabaseFavoriteRepository.exists/get_all 등 DB 접근 실패 지점에서 raise 하며,
    출력은 status_code=503 + 공통 에러 코드로 envelope 핸들러에서 응답된다.
    """

    def __init__(self, message: str = "즐겨찾기 저장소에 일시적 장애가 발생했습니다. 잠시 후 다시 시도해주세요."):
        super().__init__(
            status_code=503,
            error_code=ErrorCode.COMMON_INTERNAL_ERROR,
            message=message,
        )
