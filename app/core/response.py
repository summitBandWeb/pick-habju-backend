from typing import TypeVar, Generic, Optional, Any
from pydantic import BaseModel, ConfigDict
from app.core.error_codes import ErrorCode

T = TypeVar('T')

class ApiResponse(BaseModel, Generic[T]):
    """
    API 공통 응답 모델 (Envelope Pattern)
    
    모든 API 응답은 이 구조를 따릅니다.
    
    Attributes:
        isSuccess (bool): 성공 여부 (true/false)
        code (str): 응답 코드 (성공: "COMMON200", 실패: 에러코드)
        message (str): 메시지 (사용자 노출 가능)
        result (T | None): 실제 데이터 (실패 시에는 에러 상세 정보 또는 null)
        
    Rationale:
        - 프론트엔드에서 일관된 방식으로 응답을 처리할 수 있도록 Envelope Pattern 적용
        - Generic을 사용하여 타입 안전성 보장
        - Swagger UI에서 자동으로 타입 정보와 예시가 표시되도록 model_config 설정
    """
    isSuccess: bool
    code: str
    message: str
    result: Optional[T] = None
    
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "isSuccess": True,
                    "code": "COMMON200",
                    "message": "성공입니다.",
                    "result": {
                        "data": "example data"
                    }
                },
                {
                    "isSuccess": False,
                    "code": "VALIDATION_ERROR",
                    "message": "입력값을 확인해주세요.",
                    "result": {
                        "field": "에러 상세 정보"
                    }
                }
            ]
        }
    )


def success_response(result: T, code: str = ErrorCode.COMMON_SUCCESS, message: str = "성공입니다.") -> ApiResponse[T]:
    """
    성공 응답 생성 팩토리 함수
    
    Args:
        result: 실제 응답 데이터
        code: 응답 코드 (기본값: ErrorCode.COMMON_SUCCESS)
        message: 성공 메시지 (기본값: "성공입니다.")
        
    Returns:
        ApiResponse: 표준 성공 응답 객체
    """
    return ApiResponse(
        isSuccess=True,
        code=code,
        message=message,
        result=result
    )


def error_response(message: str, code: str = "ERROR", result: Optional[T] = None) -> ApiResponse[T]:
    """
    실패 응답 생성 팩토리 함수
    
    Args:
        message: 에러 메시지
        code: 에러 코드 (기본값: "ERROR")
        result: 에러 상세 정보 (선택사항)
        
    Returns:
        ApiResponse: 표준 실패 응답 객체
    """
    return ApiResponse(
        isSuccess=False,
        code=code,
        message=message,
        result=result
    )
