from supabase import create_client, Client
from app.core.config import SUPABASE_URL, SUPABASE_KEY
from typing import Optional

_supabase_client: Optional[Client] = None

def get_supabase_client() -> Client:
    """Supabase 클라이언트를 반환하는 팩토리 함수"""
    global _supabase_client
    if _supabase_client is None:
        if not SUPABASE_URL or not SUPABASE_KEY:
            raise ValueError("Supabase 설정이 올바르지 않습니다.")
        _supabase_client = create_client(SUPABASE_URL, SUPABASE_KEY)
    return _supabase_client

# 기존 코드 호환성을 위한 별칭
supabase = get_supabase_client()