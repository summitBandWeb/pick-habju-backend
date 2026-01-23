from supabase import create_client, Client
from app.core.config import SUPABASE_URL, SUPABASE_KEY

# 싱글톤 클라이언트 인스턴스
_supabase_client: Client | None = None

def get_supabase_client() -> Client:
    """Supabase 클라이언트 반환 (Lazy Loading & Singleton)"""
    global _supabase_client
    
    if _supabase_client is None:
        if not SUPABASE_URL or not SUPABASE_KEY:
            raise ValueError("SUPABASE_URL and SUPABASE_KEY must be set in environment variables")
        
        _supabase_client = create_client(SUPABASE_URL, SUPABASE_KEY)
    
    return _supabase_client
