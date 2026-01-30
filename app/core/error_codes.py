"""
에러 코드 상수 정의

매직 스트링 대신 상수를 사용하여 오타 방지 및 일관성 확보

Rationale:
    - 에러 코드를 한 곳에서 관리하여 변경 시 영향 범위 최소화
    - IDE 자동완성으로 오타 방지
    - 코드 리뷰 시 에러 코드 의미 파악 용이
"""

class ErrorCode:
    """에러 코드 상수 클래스"""
    
    # 공통 성공 코드
    COMMON_SUCCESS = "COMMON200"  # 모든 API 성공 응답에 사용
    
    # 공통 에러 코드
    INTERNAL_ERROR = "COMMON-001"    # 500 서버 내부 오류
    VALIDATION_ERROR = "VALIDATION-001"  # 422 요청 검증 실패
    
    @staticmethod
    def http_error(status_code: int) -> str:
        """
        HTTP 상태 코드 기반 에러 코드 생성
        
        Args:
            status_code: HTTP 상태 코드 (예: 400, 404, 500)
            
        Returns:
            str: 에러 코드 (예: "HTTP_400", "HTTP_404")
        """
        return f"HTTP_{status_code}"
