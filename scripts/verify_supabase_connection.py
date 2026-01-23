import sys
import os

# 현재 스크립트의 상위 디렉터리(프로젝트 루트)를 path에 추가
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.supabase import get_supabase_client

def verify():
    """
    Supabase 연결 상태를 검증하는 유틸리티 스크립트.
    보안을 위해 API Key는 출력하지 않으며, 실제 DB 연결 여부(Connection Probe)를 테스트합니다.
    """
    print("Verifying Supabase Connection...")
    try:
        # 1. 클라이언트 초기화
        client = get_supabase_client()
        print("✅ Client Initialization: Success")
        
        # 2. 실제 DB 연결 테스트 (favorites 테이블 조회)
        # 데이터가 없어도 에러가 나지 않는지(테이블 존재 여부 및 권한) 확인
        client.table("favorites").select("id").limit(1).execute()
        print("✅ Database Connection: Success")
        
    except Exception as e:
        print(f"❌ Connection Failed: {e}")
        sys.exit(1)

if __name__ == "__main__":
    verify()
