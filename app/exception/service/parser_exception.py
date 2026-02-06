from app.exception.base_exception import BaseCustomException, ErrorCode


class ParserException(BaseCustomException):
    """LLM 파싱 중 발생하는 예외"""
    def __init__(self, message: str = "LLM 파싱 중 오류가 발생했습니다."):
        super().__init__(
            message=message,
            error_code=ErrorCode.PARSER_ERROR,
            status_code=500
        )


class ParserTimeoutError(BaseCustomException):
    """LLM 응답 타임아웃 예외"""
    def __init__(self, message: str = "LLM 응답 타임아웃이 발생했습니다."):
        super().__init__(
            message=message,
            error_code=ErrorCode.PARSER_TIMEOUT,
            status_code=504
        )


class ParserInvalidResponseError(BaseCustomException):
    """LLM 응답 파싱 실패 예외"""
    def __init__(self, message: str = "LLM 응답을 파싱할 수 없습니다."):
        super().__init__(
            message=message,
            error_code=ErrorCode.PARSER_INVALID_RESPONSE,
            status_code=422
        )
