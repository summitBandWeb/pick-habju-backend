import sys
import os

# 현재 디렉토리를 path에 추가하여 app 모듈 찾기 가능하게 함
sys.path.append(os.getcwd())

from app.core.supabase import get_supabase_client

def verify():
    print("Verifying Supabase Connection...")
    try:
        # 1. 클라이언트 초기화 시도
        client = get_supabase_client()
        print("✅ Client Initialization: Success")
        
        # 2. URL/Key 마스킹하여 출력 확인
        url = client.supabase_url
        key = client.supabase_key
        print(f"ℹ️  Supabase URL: {url[:8]}...{url[-5:] if url else ''}")
        print(f"ℹ️  Supabase Key: {'Loaded' if key else 'Missing'}")
        
    except Exception as e:
        print(f"❌ Connection Failed: {e}")
        sys.exit(1)

if __name__ == "__main__":
    verify()
