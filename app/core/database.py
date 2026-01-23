from supabase import create_client, Client
from app.core.config import SUPABASE_URL, SUPABASE_KEY

# 클라이언트 인스턴스 생성
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)