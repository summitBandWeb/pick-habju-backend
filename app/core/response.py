from typing import TypeVar, Generic, Optional, Any
from pydantic import BaseModel, ConfigDict
from app.core.error_codes import ErrorCode

# Rationale:
# ApiResponse의 result 필드에 Pydantic 모델뿐만 아니라 Dict[str, bool] 등의 일반 Python 타입을 
# 유연하게 허용하기 위해 bound=BaseModel 제약을 제거했습니다.
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
        - Pydantic 모델뿐만 아니라 Dict, List 등 일반 타입을 유연하게 지원하기 위해 Generic[T]의 제약(bound=BaseModel)을 제거함
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
                        "field_name": {
                            "message": "에러 메시지",
                            "type": "error_type",
                            "input": "provided_input"
                        }
                    }
                }
            ]
        }
    )

    @classmethod
    def success(cls, result: Any = None, code: str = ErrorCode.COMMON_SUCCESS, message: str = "성공입니다.") -> "ApiResponse[Any]":
        """
        성공 응답 생성을 위한 클래스 메서드 (하위 호환성 유지용)
        """
        return cls(
            isSuccess=True,
            code=code,
            message=message,
            result=result
        )

    @classmethod
    def error(cls, code: str = "ERROR", message: str = "에러가 발생했습니다.", result: Any = None) -> "ApiResponse[Any]":
        """
        실패 응답 생성을 위한 클래스 메서드 (하위 호환성 유지용)
        """
        return cls(
            isSuccess=False,
            code=code,
            message=message,
            result=result
        )


class ValidationErrorDetail(BaseModel):
    """
    Validation 에러의 상세 정보를 담는 모델
    """
    message: str
    type: str
    input: Any | None = None


def success_response(result: T, code: str = ErrorCode.COMMON_SUCCESS, message: str = "성공입니다.") -> ApiResponse[T]:
    """
    성공 응답 생성 팩토리 함수 (신규 표준)
    """
    return ApiResponse.success(result=result, code=code, message=message)


def error_response(message: str, code: str = "ERROR", result: Optional[Any] = None) -> ApiResponse[Any]:
    """
    실패 응답 생성 팩토리 함수 (신규 표준)
    """
    return ApiResponse.error(code=code, message=message, result=result)
