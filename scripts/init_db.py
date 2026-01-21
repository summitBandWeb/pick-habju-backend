from app.core.database import engine, Base
from app.models.favorite import Favorite

def init_db():
    """데이터베이스 테이블을 초기화합니다.

    Summary:
        SQLAlchemy 모델 메타데이터를 기반으로 DB 테이블을 생성합니다.

    Rationale:
        로컬 개발 환경에서 빠르게 DB 스키마를 생성하고 검증하기 위한 유틸리티 스크립트입니다.
        프로덕션 환경에서는 Alembic 같은 마이그레이션 도구를 사용하는 것을 권장합니다.
    """
    print("Creating tables...")
    try:
        # NOTE: bind=engine을 명시하여 해당 엔진에 연결된 DB에 테이블을 생성함
        Base.metadata.create_all(bind=engine)
        print("Tables created successfully.")
    except Exception as e:
        print(f"Error creating tables: {e}")

if __name__ == "__main__":
    # NOTE: 루트 디렉토리에서 'python -m scripts.init_db' 명령어로 실행해야 함
    init_db()
