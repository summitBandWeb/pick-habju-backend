<<<<<<< HEAD
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
=======
import os
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

# NOTE: SQLite 파일 저장 경로. 컨테이너 배포 시 볼륨 마운트 경로 확인 필요.
# Rationale: 환경 변수(DATABASE_URL)를 우선 사용하여, 테스트/배포 환경별 DB를 유동적으로 교체할 수 있도록 개선함.
SQLALCHEMY_DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./pickhabju.db")

# Rationale:
# SQLite는 기본적으로 단일 스레드에서만 연결을 허용합니다(check_same_thread=True).
# 하지만 FastAPI는 비동기 요청 처리 시 ThreadPoolExecutor를 사용하므로,
# 하나의 요청 내에서도 여러 스레드가 DB 커넥션을 공유할 수 있어야 합니다.
# 따라서 check_same_thread=False 옵션을 통해 멀티 스레드환경 접근을 허용합니다.
#
# CAUTION:
# SQLite는 동시 쓰기(concurrent writes)에 취약합니다.
# 현재 개발 단계에서는 괜찮지만, 프로덕션에서는 PostgreSQL/MySQL 사용을 권장합니다.
# 동시 사용자가 많아지면 'database is locked' 오류가 발생할 수 있습니다.
engine = create_engine(
    SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False}
)

# NOTE: 요청마다 독립적인 세션을 생성하기 위해 SessionLocal 팩토리를 사용함.
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

def get_db():
    """FastAPI 의존성 주입용 DB 세션 제공 함수입니다.

    Yields:
        Session: 요청별로 생성된 독립적인 DB 세션.

    Rationale:
        FastAPI의 Depends를 통해 세션 생명주기를 자동으로 관리하기 위해 사용합니다.
        try-finally 블록을 사용하여 요청 처리 후 반드시 세션이 닫히도록(close) 보장합니다.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
>>>>>>> 84dea54 ([#102]; refactor: DB 설정 개선 (get_db, Env var, SQLite 경고 추가))
