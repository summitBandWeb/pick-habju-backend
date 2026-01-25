import uuid
import pytest
import time
from app.repositories.supabase import SupabaseFavoriteRepository
from unittest.mock import MagicMock, patch
import concurrent.futures
# config.py에서 변수를 직접 가져오거나, repository 내부 동작에 의존
# 일반적으로 config가 로드되어야 repository가 동작함

# 환경변수 확인을 위한 간단한 체크
from app.core.config import SUPABASE_URL, SUPABASE_KEY

@pytest.mark.skipif(
    not SUPABASE_URL or not SUPABASE_KEY,
    reason="Supabase 환경 변수(SUPABASE_URL, SUPABASE_KEY)가 설정되지 않아 통합 테스트를 건너뜁니다."
)
class TestSupabaseIntegration:
    """
    [Integration Test] Supabase Repository
    실제 Supabase 인스턴스와 통신하여 CRUD가 정상적으로 동작하는지 검증합니다.
    
    NOTE: 이 테스트는 실제 DB 데이터를 조작하므로, 운영 환경 DB가 아닌 
    테스트용 프로젝트 혹은 테스트용 계정에서 수행하는 것을 권장합니다.
    """

    @pytest.fixture
    def repo(self):
        return SupabaseFavoriteRepository()

    @pytest.fixture
    def test_identifiers(self, repo):
        """테스트 데이터 생성 및 정리 (Teardown guaranteed)"""
        ids = {
            "user_id": f"test_user_{uuid.uuid4()}",
            "biz_item_id": f"test_biz_{uuid.uuid4()}"
        }
        
        yield ids
        
        # Teardown: 테스트 종료 후(성공/실패 무관) 데이터 정리 시도
        try:
            repo.delete(ids["user_id"], ids["biz_item_id"])
            # 추가된 파생 데이터(multiple favorites 등)도 필요한 경우 여기서 정리 가능하지만,
            # 개별 테스트 메서드에서 생성한 unique ID들이라 해당 메서드 로직에 의존적일 수 있음.
            # 기본적인 id 세트는 여기서 정리 보장.
        except Exception as e:
            print(f"Teardown failed: {e}")

    def test_favorite_lifecycle(self, repo, test_identifiers):
        """
        즐겨찾기 전체 라이프사이클 테스트
        1. 초기 상태: 없어야 함
        2. 추가 (Add): 성공해야 함
        3. 조회 (Exists): 있어야 함
        4. 목록 조회 (Get All): 리스트에 포함되어야 함
        5. 중복 추가: 실패(False)해야 함
        6. 삭제 (Delete): 성공해야 함
        7. 최종 확인: 없어야 함
        """
        user_id = test_identifiers["user_id"]
        biz_id = test_identifiers["biz_item_id"]

        print(f"\n[Test] Testing with User: {user_id}, Item: {biz_id}")

        # 1. Clean verify (혹시 모를 잔여 데이터 확인)
        initial_exists = repo.exists(user_id, biz_id)
        assert not initial_exists, "테스트 시작 전 데이터가 존재하면 안 됩니다."

        # 2. Add
        added = repo.add(user_id, biz_id)
        assert added is True, "첫 데이터 추가는 성공해야 합니다."

        # 3. Exists
        exists = repo.exists(user_id, biz_id)
        assert exists is True, "추가된 데이터는 존재해야 합니다."

        # 4. Get All
        favorites = repo.get_all(user_id)
        assert biz_id in favorites, "전체 목록 조회 결과에 추가한 아이템이 있어야 합니다."

        # 5. Duplicate Add Check (Upsert -> Idempotency)
        duplicate_added = repo.add(user_id, biz_id)
        assert duplicate_added is True, "이미 존재하더라도 멱등성에 의해 True(성공)를 반환해야 합니다."

        # 6. Delete
        repo.delete(user_id, biz_id)
        
        # 7. Verify Deletion
        exists_after_delete = repo.exists(user_id, biz_id)
        assert exists_after_delete is False, "삭제 후에는 데이터가 존재하지 않아야 합니다."
        
        favorites_after_delete = repo.get_all(user_id)
        assert biz_id not in favorites_after_delete, "삭제 후 목록 조회 결과에 아이템이 없어야 합니다."

    def test_get_all_multiple_favorites(self, repo, test_identifiers):
        """한 사용자가 여러 즐겨찾기를 갖는 경우"""
        user_id = test_identifiers["user_id"]
        biz_ids = [f"{test_identifiers['biz_item_id']}_{i}" for i in range(3)]

        print(f"\n[Test] Multiple Favorites for User: {user_id}")
        
        # 1. Add Multiple
        for biz_id in biz_ids:
            repo.add(user_id, biz_id)
        
        # 2. Get All
        favorites = repo.get_all(user_id)
        
        # 3. Verify
        assert len(favorites) >= 3, "최소 3개 이상의 즐겨찾기가 조회되어야 합니다."
        for biz_id in biz_ids:
            assert biz_id in favorites, f"추가한 아이템({biz_id})이 목록에 포함되어야 합니다."

    def test_concurrent_add_operations(self, repo, test_identifiers):
        """동시 추가 요청 처리 (race condition / idempotency 테스트)"""
        user_id = test_identifiers["user_id"]
        biz_id = test_identifiers["biz_item_id"]
        
        print(f"\n[Test] Concurrent Add for User: {user_id}")

        def add_task():
            return repo.add(user_id, biz_id)

        # 동시에 5번 추가 요청
        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(add_task) for _ in range(5)]
            results = [f.result() for f in concurrent.futures.as_completed(futures)]
        
        # 모두 True(성공)여야 함 (Upsert 덕분에 에러 없이 처리됨)
        assert all(results) is True, "동시 요청 시에도 모두 True를 반환해야 합니다 (Upsert)."
        
        # 실제 데이터는 1개만 존재해야 함 (논리적 확인) - Exists로 체크
        assert repo.exists(user_id, biz_id) is True
        
        # Duplicate check - count logic depends on implementation, 
        # but here we ensure no errors occurred and data exists.

        # Cleanup
        repo.delete(user_id, biz_id)

    def test_error_handling_invalid_data(self, repo):
        """잘못된 데이터 입력 시 에러 처리"""
        # 아주 긴 문자열이나 None 등 (Supabase-py Client 레벨에서 걸러질 수 있음)
        # 여기서는 Client 객체를 Mocking해서 강제로 에러를 발생시켜
        # Repository가 예외를 잘 잡아서 로깅하고 re-raise 하는지 확인해도 됨.
        # 하지만 Integration Test이므로 실제 DB 제약조건 위반 등을 시도.
        
        # 예: user_id가 None인 경우 (타입 힌트상 str이지만 런타임에 None 전달)
        # Supabase Client가 400 Bad Request 등을 뱉을 수 있음.
        
    def test_database_connection_failure(self):
        """DB 연결 실패 테스트 (Mocking)"""
        # Repository 인스턴스를 생성하되, 내부 client를 Mock으로 교체
        repo = SupabaseFavoriteRepository()
        
        # 특정 메서드 호출 시 예외 발생하도록 설정
        # Supabase client의 table().upsert().execute() 체인을 Mocking
        mock_client = MagicMock()
        mock_client.table.return_value.upsert.return_value.execute.side_effect = Exception("Connection Refused")
        
        # Mock Client 주입
        repo.client = mock_client
        
        print(f"\n[Test] Database Connection Failure Simulation")

        with pytest.raises(Exception) as excinfo:
            repo.add("test_user_error", "test_item_error")
        
        assert "Connection Refused" in str(excinfo.value)

    def test_performance_large_data(self, repo, test_identifiers):
        """대량 데이터 조회 성능 테스트 (50개)"""
        user_id = test_identifiers["user_id"]
        # 테스트용 데이터 50개 생성
        items = [f"perf_item_{i}" for i in range(50)]
        
        print(f"\n[Test] Performance Test with 50 items")
        
        # 1. Bulk Insert (Upsert로 하나씩 넣는 시간 측정)
        start_time = time.time()
        for item in items:
            repo.add(user_id, item)
        duration_add = time.time() - start_time
        print(f"  - Add 50 items: {duration_add:.4f} sec")
        
        # 2. Get All Performance
        start_time = time.time()
        favorites = repo.get_all(user_id)
        duration_get = time.time() - start_time
        print(f"  - Get 50 items: {duration_get:.4f} sec")
        
        assert len(favorites) == 50
        assert duration_get < 1.0, "50개 조회는 1초 이내여야 합니다." # 기준은 환경에 따라 조절

        # Cleanup
        for item in items:
            repo.delete(user_id, item)

    def test_concurrent_delete_operations(self, repo, test_identifiers):
        """동시 삭제 요청 처리 (Race Condition 테스트)"""
        user_id = test_identifiers["user_id"]
        biz_id = test_identifiers["biz_item_id"]
        
        # 먼저 데이터 추가
        repo.add(user_id, biz_id)
        assert repo.exists(user_id, biz_id) is True
        
        print(f"\n[Test] Concurrent Delete for User: {user_id}")

        def delete_task():
            # 삭제는 리턴이 None이지만 에러가 안나야 함
            repo.delete(user_id, biz_id)
            return True

        # 동시에 5번 삭제 요청
        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(delete_task) for _ in range(5)]
            results = [f.result() for f in concurrent.futures.as_completed(futures)]
            
        assert all(results), "동시 삭제 요청 시 에러가 없어야 합니다."
        
        # 최종적으로 데이터가 없어야 함
        assert repo.exists(user_id, biz_id) is False