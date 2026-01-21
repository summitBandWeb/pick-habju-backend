from datetime import datetime
from sqlalchemy import Column, Integer, String, UniqueConstraint, DateTime
from app.core.database import Base

class Favorite(Base):
    """사용자의 즐겨찾기 정보를 저장하는 테이블 모델입니다.

    Args:
        id (int): 레코드 고유 ID (PK, Auto Increment).
        user_id (str): 사용자 식별값. 프론트엔드 Header(X-Device-Id)에서 전달받은 UUID.
        biz_item_id (str): 외부 크롤링 소스(Naver/Dream/Groove)의 고유 합주실 ID.
        created_at (datetime): 즐겨찾기 최초 생성 일시.
        updated_at (datetime): 즐겨찾기 정보 수정 일시.

    Rationale:
        별도의 회원가입 절차 없이 기기 고유 ID(UUID)를 기준으로 즐겨찾기를 관리합니다.
        따라서 User 테이블과의 Foreign Key 대신 단순 String 타입의 user_id를 사용합니다.
    """
    __tablename__ = "favorites"
    __table_args__ = (
        # Rationale:
        # 한 유저가 동일한 합주실을 중복해서 즐겨찾기 할 수 없도록 물리적 제약조건을 설정함.
        # 이를 통해 애플리케이션 레벨의 중복 검사 로직 누락 시에도 데이터 정합성을 보장함.
        UniqueConstraint('user_id', 'biz_item_id', name='uq_user_device_biz_item'),
    )

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    
    # Rationale: UUID(36) 및 외부 ID 길이를 고려하여 255자로 제한 (타 DB 마이그레이션 대비)
    user_id = Column(String(255), nullable=False, index=True) 
    biz_item_id = Column(String(255), nullable=False)
    
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
