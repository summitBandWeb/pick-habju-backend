import os
import uuid
import pytest
from app.repositories.supabase import SupabaseFavoriteRepository
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
    def test_identifiers(self):
        """테스트에 사용할 고유한 사용자 ID와 아이템 ID 생성"""
        # 충돌 방지를 위해 UUID 사용
        return {
            "user_id": f"test_user_{uuid.uuid4()}",
            "biz_item_id": f"test_biz_{uuid.uuid4()}"
        }

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

        # 5. Duplicate Add Check
        duplicate_added = repo.add(user_id, biz_id)
        assert duplicate_added is False, "이미 존재하는 데이터를 추가하면 False를 반환해야 합니다."

        # 6. Delete
        repo.delete(user_id, biz_id)
        
        # 7. Verify Deletion
        exists_after_delete = repo.exists(user_id, biz_id)
        assert exists_after_delete is False, "삭제 후에는 데이터가 존재하지 않아야 합니다."
        
        favorites_after_delete = repo.get_all(user_id)
        assert biz_id not in favorites_after_delete, "삭제 후 목록 조회 결과에 아이템이 없어야 합니다."
