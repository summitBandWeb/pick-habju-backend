import pytest
from pydantic import BaseModel, ValidationError
from app.core.response import ApiResponse, success_response, error_response
from app.core.error_codes import ErrorCode

class DataModel(BaseModel):
    """테스트용 데이터 모델"""
    data: str

class RoomsModel(BaseModel):
    """테스트용 Rooms 모델"""
    rooms: list

class IdModel(BaseModel):
    """테스트용 ID 모델"""
    id: int

class EmptyModel(BaseModel):
    """빈 모델"""
    pass

class ValidationErrorDetail(BaseModel):
    """Validation 에러 상세 정보"""
    message: str
    type: str
    input: str | None

class ValidationErrorResult(BaseModel):
    """Validation 에러 result 모델"""
    query_date: ValidationErrorDetail | None = None

def test_success_response_basic():
    """기본 성공 응답 생성 테스트"""
    test_data = DataModel(data="test")
    response = success_response(result=test_data)
    
    assert response.isSuccess is True
    assert response.code == ErrorCode.COMMON_SUCCESS
    assert response.message == "성공입니다."
    assert response.result.data == "test"

def test_success_response_custom_message():
    """커스텀 메시지 테스트"""
    test_data = RoomsModel(rooms=[])
    response = success_response(
        result=test_data,
        message="조회 완료"
    )
    
    assert response.isSuccess is True
    assert response.message == "조회 완료"
    assert response.code == ErrorCode.COMMON_SUCCESS


def test_success_response_custom_code():
    """커스텀 코드 테스트"""
    test_data = IdModel(id=123)
    response = success_response(
        result=test_data,
        code="CUSTOM_201",
        message="생성 완료"
    )
    
    assert response.code == "CUSTOM_201"
    assert response.message == "생성 완료"
    assert response.result.id == 123


def test_success_response_none_result():
    """result가 None인 경우 테스트 (삭제 API 등)"""
    class EmptyModel(BaseModel):
        pass
    
    response = success_response(
        result=EmptyModel(),
        message="삭제 완료"
    )
    
    assert response.isSuccess is True
    assert response.message == "삭제 완료"

def test_error_response_basic():
    """기본 에러 응답 생성 테스트"""
    response = error_response(message="에러 발생", code="TEST_ERROR")
    
    assert response.isSuccess is False
    assert response.code == "TEST_ERROR"
    assert response.message == "에러 발생"
    assert response.result is None

def test_error_response_with_result():
    """리절트에 상세 정보가 있는 에러 (Validation 에러 등)"""
    error_detail = ValidationErrorDetail(
        message="Invalid format",
        type="value_error",
        input="2026/01/28"
    )
    error_data = ValidationErrorResult(query_date=error_detail)
    
    response = error_response(
        message="입력값을 확인해주세요.",
        code=ErrorCode.VALIDATION_ERROR,
        result=error_data
    )
    
    assert response.isSuccess is False
    assert response.code == ErrorCode.VALIDATION_ERROR
    assert response.result.query_date.message == "Invalid format"

def test_error_code_constants():
    """에러 코드 상수 값 검증"""
    assert ErrorCode.COMMON_SUCCESS == "COMMON200"
    assert ErrorCode.INTERNAL_ERROR == "COMMON-001"
    assert ErrorCode.VALIDATION_ERROR == "VALIDATION-001"

def test_error_code_http_error():
    """HTTP 상태 코드 기반 에러 코드 생성"""
    assert ErrorCode.http_error(400) == "HTTP_400"
    assert ErrorCode.http_error(404) == "HTTP_404"
    assert ErrorCode.http_error(500) == "HTTP_500"

def test_api_response_model_direct():
    """ApiResponse 모델을 직접 생성"""
    test_data = DataModel(data="value")
    response = ApiResponse(
        isSuccess=True,
        code="TEST_CODE",
        message="테스트",
        result=test_data
    )
    
    assert response.isSuccess is True
    assert response.code == "TEST_CODE"
    assert response.result.data == "value"

def test_api_response_json_serialization():
    """JSON 직렬화 테스트"""
    test_data = IdModel(id=123)
    response = success_response(result=test_data)
    
    # model_dump(mode='json')로 JSON 직렬화
    dumped = response.model_dump(mode='json')
    
    assert isinstance(dumped, dict)
    assert dumped["isSuccess"] is True
    assert dumped["code"] == ErrorCode.COMMON_SUCCESS
    assert dumped["result"]["id"] == 123

def test_api_response_field_order():
    """JSON 직렬화 시 필드 순서 확인 (isSuccess → code → message → result)"""
    test_data = DataModel(data="test")
    response = success_response(result=test_data)
    
    # model_dump(mode='json')로 직렬화
    dumped = response.model_dump(mode='json')
    keys = list(dumped.keys())
    
    assert keys == ["isSuccess", "code", "message", "result"]

def test_success_response_empty_dict():
    """빈 딕셔너리 result"""
    class EmptyDict(BaseModel):
        pass
    
    response = success_response(result=EmptyDict())
    assert response.result is not None

def test_error_response_long_message():
    """긴 에러 메시지 처리"""
    long_message = "에러 " * 100
    response = error_response(message=long_message, code="LONG_ERROR")
    
    assert response.message == long_message
    assert len(response.message) > 100

def test_error_response_special_characters():
    """특수문자가 포함된 메시지"""
    special_msg = "에러: [중요] 'value' is <invalid> & \"wrong\""
    response = error_response(message=special_msg, code="SPECIAL_ERROR")
    
    assert response.message == special_msg