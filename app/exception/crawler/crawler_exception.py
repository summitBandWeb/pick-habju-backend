from app.exception.base_exception import BaseCustomException, ErrorCode


class CrawlerException(BaseCustomException):
    """크롤링 로직 수행 중 발생하는 일반 예외.

    Rationale (의도):
        - 특정 크롤러(Naver, Groove 등)에 종속되지 않는 공통적인 크롤링 오류를 처리합니다.
    """
    def __init__(self, message: str = "크롤링 중 오류가 발생했습니다."):
        super().__init__(
            message=message,
            error_code=ErrorCode.CRAWLER_EXECUTION_FAILED,
            status_code=500
        )


class CrawlerTimeoutError(BaseCustomException):
    """크롤링 작업 시간이 초과되었을 때 발생하는 예외.

    Rationale (의도):
        - 외부 사이트의 응답 지연으로 인해 전체 시스템이 블로킹되는 것을 방지하기 위해
          설정된 타임아웃 임계값을 초과하면 발생합니다.
        - 이는 504 Gateway Timeout으로 매핑되어 적절한 HTTP 응답을 제공합니다.
    """
    def __init__(self, message: str = "크롤링 타임아웃이 발생했습니다."):
        super().__init__(
            message=message,
            error_code=ErrorCode.CRAWLER_TIMEOUT,
            status_code=504
        )


class CrawlerBlockedError(BaseCustomException):
    """봇 탐지 시스템에 의해 크롤러의 접근이 차단되었을 때 발생하는 예외.

    Rationale (의도):
        - 대상 사이트(Naver 등)에서 IP 차단이나 CAPTCHA 요구 등으로 접근을 거부했을 때 사용합니다.
        - 403 Forbidden으로 응답하여 클라이언트가 접근 권한이 없음을 알립니다.
    """
    def __init__(self, message: str = "봇 감지로 인해 접근이 차단되었습니다."):
        super().__init__(
            message=message,
            error_code=ErrorCode.CRAWLER_AUTH_FAILED,
            status_code=403
        )
