import pytest
from unittest.mock import MagicMock, AsyncMock
from scripts.update_seoul_coordinates import update_district

@pytest.fixture
def mock_supabase():
    mock = MagicMock()
    # supabase.table("branch").select("business_id").eq("business_id", business_id).execute()
    mock.table.return_value.select.return_value.eq.return_value.execute.return_value.data = []
    return mock

@pytest.fixture
def mock_crawler():
    return AsyncMock()

@pytest.mark.asyncio
async def test_update_district_with_valid_data(mock_supabase, mock_crawler):
    """정상적인 좌표 데이터가 있을 때 성공적으로 처리되는지 확인"""
    # Given: 정상 검색 결과
    mock_crawler.search_rehearsal_rooms.return_value = [
        {"id": "test123", "name": "테스트합주실", "x": "127.0", "y": "37.5"}
    ]
    
    # When
    success, failure = await update_district("강남구 합주실", mock_supabase, mock_crawler)
    
    # Then
    assert success == 1
    assert failure == 0
    # supabase.table("branch").insert({...}).execute() 호출 확인
    mock_supabase.table.assert_called_with("branch")
    assert mock_supabase.table().insert.called

@pytest.mark.asyncio
async def test_update_district_with_missing_coordinates(mock_supabase, mock_crawler):
    """좌표 데이터가 누락되었을 때 예외 없이 스킵되는지 확인"""
    # Given: 좌표 없는 데이터
    mock_crawler.search_rehearsal_rooms.return_value = [
        {"id": "test456", "name": "좌표없음", "x": None, "y": None}
    ]
    
    # When
    success, failure = await update_district("강남구 합주실", mock_supabase, mock_crawler)
    
    # Then
    assert success == 0
    assert failure == 1
    # DB 작업이 호출되지 않았어야 함
    assert not mock_supabase.table().insert.called
    assert not mock_supabase.table().update.called

@pytest.mark.asyncio
async def test_update_district_out_of_range(mock_supabase, mock_crawler):
    """서울 범위를 벗어난 좌표 데이터가 있을 때 스킵되는지 확인"""
    # Given: 서울 범위를 벗어난 데이터 (부산 좌표 등)
    mock_crawler.search_rehearsal_rooms.return_value = [
        {"id": "busan123", "name": "부산합주실", "x": "129.0", "y": "35.1"}
    ]
    
    # When
    success, failure = await update_district("강남구 합주실", mock_supabase, mock_crawler)
    
    # Then
    assert success == 0
    assert failure == 1
    assert not mock_supabase.table().insert.called
    assert not mock_supabase.table().update.called

@pytest.mark.asyncio
async def test_update_district_existing_branch(mock_supabase, mock_crawler):
    """이미 존재하는 지점일 경우 좌표만 업데이트하고 이름은 건드리지 않는지 확인"""
    # Given: 이미 존재하는 데이터
    mock_crawler.search_rehearsal_rooms.return_value = [
        {"id": "existing123", "name": "새로운이름", "x": "127.1", "y": "37.6"}
    ]
    # existing.data가 비어있지 않게 설정
    mock_supabase.table.return_value.select.return_value.eq.return_value.execute.return_value.data = [{"business_id": "existing123"}]
    
    # When
    success, failure = await update_district("강남구 합주실", mock_supabase, mock_crawler)
    
    # Then
    assert success == 1
    assert failure == 0
    # update가 호출되었는지 확인
    mock_supabase.table().update.assert_called_with({
        "lat": 37.6,
        "lng": 127.1
    })
    # insert는 호출되지 않아야 함
    assert not mock_supabase.table().insert.called
