from app.exception.base_exception import BaseCustomException


class ParserException(BaseCustomException):
    """LLM 파싱 중 발생하는 예외"""
    error_code = "PARSER-001"
    message = "LLM 파싱 중 오류가 발생했습니다."
    status_code = 500


class ParserTimeoutError(BaseCustomException):
    """LLM 응답 타임아웃 예외"""
    error_code = "PARSER-002"
    message = "LLM 응답 타임아웃이 발생했습니다."
    status_code = 504


class ParserInvalidResponseError(BaseCustomException):
    """LLM 응답 파싱 실패 예외"""
    error_code = "PARSER-003"
    message = "LLM 응답을 파싱할 수 없습니다."
    status_code = 422
