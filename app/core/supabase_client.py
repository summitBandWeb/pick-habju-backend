from functools import lru_cache
from supabase import create_client, Client, ClientOptions
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
        - ClientOptions를 통한 HTTP 클라이언트 설정 (v2 권장 방식)
    """
    if not SUPABASE_URL or not SUPABASE_KEY:
        raise ValueError("SUPABASE_URL and SUPABASE_KEY must be set in environment variables")
    
    # v2 권장 방식: ClientOptions를 사용하여 HTTP 클라이언트 설정
    options = ClientOptions(
        schema="public",  # 기본 스키마
        auto_refresh_token=True,  # 자동 토큰 갱신
        persist_session=True  # 세션 유지
    )
    
    return create_client(SUPABASE_URL, SUPABASE_KEY, options=options)

# Backward compatibility alias
supabase = get_supabase_client()
