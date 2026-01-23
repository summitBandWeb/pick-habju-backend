from functools import lru_cache
from supabase import create_client, Client
from app.core.config import SUPABASE_URL, SUPABASE_KEY

@lru_cache
def get_supabase_client() -> Client:
    """
    Supabase 클라이언트 반환 (Singleton via lru_cache)
    
    Returns:
        Client: Supabase Client 인스턴스
        
    Rationale:
        - functools.lru_cache를 사용하여 Thread-safe한 싱글톤 패턴 구현
        - 멀티스레드 환경(FastAPI)에서의 Race Condition 방지
    """
    if not SUPABASE_URL or not SUPABASE_KEY:
        raise ValueError("SUPABASE_URL and SUPABASE_KEY must be set in environment variables")
    
    return create_client(SUPABASE_URL, SUPABASE_KEY)
