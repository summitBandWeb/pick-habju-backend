from app.exception.base_exception import BaseCustomException


class CrawlerException(BaseCustomException):
    """크롤링 중 발생하는 예외"""
    error_code = "CRAWLER-001"
    message = "크롤링 중 오류가 발생했습니다."
    status_code = 500


class CrawlerTimeoutError(BaseCustomException):
    """크롤링 타임아웃 예외"""
    error_code = "CRAWLER-002"
    message = "크롤링 타임아웃이 발생했습니다."
    status_code = 504


class CrawlerBlockedError(BaseCustomException):
    """봇 감지로 인한 차단 예외"""
    error_code = "CRAWLER-003"
    message = "봇 감지로 인해 접근이 차단되었습니다."
    status_code = 403
