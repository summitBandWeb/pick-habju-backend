from enum import Enum

class ErrorCode(str, Enum):
    """
    애플리케이션 전반에서 사용하는 에러 코드 정의.
    형식: 카테고리(영문)-번호(3자리)
    """
    # 1. COMMON: 공통/일반 에러
    GENERIC_UNKNOWN = "GENERIC-000"
    COMMON_INTERNAL_ERROR = "COMMON-001"
    COMMON_BAD_REQUEST = "COMMON-002"
    
    # 2. API: API 요청/통신 관련
    API_REQUEST_FAILED = "API-001"

    # 3. CRAWLER: 크롤러 실행/파싱 관련
    CRAWLER_EXECUTION_FAILED = "CRAWLER-001"
    CRAWLER_PARSING_FAILED = "CRAWLER-002"
    CRAWLER_AUTH_FAILED = "CRAWLER-003" # 로그인/권한 실패
    CRAWLER_TIMEOUT = "CRAWLER-004"     # 타임아웃
    
    # 4. PARSER: LLM 등 데이터 정제 관련
    PARSER_ERROR = "PARSER-001"
    PARSER_TIMEOUT = "PARSER-002"
    PARSER_INVALID_RESPONSE = "PARSER-003"


class BaseCustomException(Exception):
    """
    모든 커스텀 예외의 최상위 클래스.
    이 클래스를 상속받아 구체적인 예외를 정의해야 함.
    """
    error_code: ErrorCode = ErrorCode.GENERIC_UNKNOWN
    message: str = "알 수 없는 오류가 발생했습니다."
    status_code: int = 500

    def __init__(self, message: str = None, error_code: ErrorCode = None, status_code: int = None):
        if message:
            self.message = message
        if error_code:
            self.error_code = error_code
        if status_code:
            self.status_code = status_code
        super().__init__(self.message)
