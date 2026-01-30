from typing import Generic, TypeVar, Optional, Any
from pydantic import BaseModel, Field

T = TypeVar("T")

class ApiResponse(BaseModel, Generic[T]):
    """
    API 공통 응답 포맷 (Envelope Pattern)
    """
    isSuccess: bool = Field(..., description="성공 여부")
    code: str = Field(..., description="응답 코드 (성공: COMMON200, 실패: 에러코드)")
    message: str = Field(..., description="응답 메시지")
    timestamp: str = Field(..., description="응답 일시")
    result: Optional[T] = Field(None, description="실제 응답 데이터 (실패 시 null)")

    @classmethod
    def success(cls, result: T = None, message: str = "성공입니다.") -> "ApiResponse[T]":
        from datetime import datetime
        return cls(
            isSuccess=True,
            code="COMMON200",
            message=message,
            timestamp=datetime.now().isoformat(timespec="seconds"),
            result=result
        )

    @classmethod
    def error(cls, code: str, message: str, result: Any = None) -> "ApiResponse[None]":
        from datetime import datetime
        return cls(
            isSuccess=False,
            code=code,
            message=message,
            timestamp=datetime.now().isoformat(timespec="seconds"),
            result=result
        )
