"""
테스트용 API 엔드포인트 (/api/test)

Issue #110: Envelope Pattern 검증을 위한 임시 엔드포인트

⚠️ 보안 경고:
    이 파일은 개발/테스트 환경 전용입니다.
    운영 환경(ENV=prod)에서는 절대 노출되어서는 안 됩니다.
    
    안전장치:
    1. main.py에서 ENV 체크로 라우터 등록 방지
    2. 모듈 로드 시 assert로 즉시 실패
    3. 접근 시 경고 로그 기록
"""
from fastapi import APIRouter, HTTPException, Query
from app.core.response import ApiResponse, success_response
import logging
import os

# 🛡️ 안전장치 1: 운영 환경에서 모듈 로드 시 즉시 실패
ENV = os.getenv("ENV", "dev")
assert ENV != "prod", "❌ CRITICAL: test_envelope.py는 운영 환경에서 로드되어서는 안 됩니다!"

logger = logging.getLogger(__name__)

# 🛡️ 안전장치 2: 테스트 라우터 로드 시 경고 로그
if ENV == "prod":
    logger.critical("🚨 SECURITY ALERT: Test endpoints loaded in production environment!")
else:
    logger.info(f"✅ Test endpoints loaded (ENV={ENV})")

router = APIRouter(
    prefix="/api/test",
    tags=["Test (Envelope Pattern Verification)"],
)

@router.get("/success", response_model=ApiResponse[dict])
def test_success():
    """
    성공 응답 테스트 (200 OK)
    
    Returns:
        ApiResponse: isSuccess=True, code="COMMON200"
    """
    return success_response(
        result={"message": "This is a successful test response"},
        message="테스트 성공입니다."
    )

@router.get("/error", response_model=ApiResponse[None])
def test_error(status_code: int = Query(400, description="에러 코드 (400, 404, 500 등)")):
    """
    에러 응답 테스트 (HTTPException 발생 -> Global Handler 변환)
    
    Args:
        status_code: 발생시킬 HTTP 상태 코드
        
    Raises:
        HTTPException: 지정된 상태 코드로 예외 발생
    """
    raise HTTPException(status_code=status_code, detail=f"테스트용 {status_code} 에러입니다.")

@router.get("/server-error", response_model=ApiResponse[None])
def test_server_error():
    """
    서버 에러 테스트 (500 Internal Server Error)
    
    Raises:
        Exception: 일반 예외 발생 -> Global Exception Handler 변환
    """
    raise Exception("의도적으로 발생시킨 서버 에러입니다.")
