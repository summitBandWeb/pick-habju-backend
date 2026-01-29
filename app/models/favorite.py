from pydantic import BaseModel, ConfigDict, Field
from datetime import datetime

class Favorite(BaseModel):
    """사용자의 즐겨찾기 정보를 저장하는 데이터 모델 (Pydantic)

    Args:
        id (int): 레코드 고유 ID (PK, Auto Increment).
        user_id (str): 사용자 식별값. 프론트엔드 Header(X-Device-Id)에서 전달받은 UUID.
        biz_item_id (str): 외부 크롤링 소스(Naver/Dream/Groove)의 고유 합주실 ID.
        created_at (datetime): 즐겨찾기 최초 생성 일시.
        updated_at (datetime): 즐겨찾기 정보 수정 일시.

    Rationale:
        별도의 회원가입 절차 없이 기기 고유 ID(UUID)를 기준으로 즐겨찾기를 관리합니다.
        따라서 User 테이블과의 Foreign Key 대신 단순 String 타입의 user_id를 사용합니다.
        
        Note: Supabase로 전환되면서 SQLAlchemy Base 대신 Pydantic BaseModel을 사용합니다.
    """
    id: int
    
    # Rationale: UUID(36) 및 외부 ID 길이를 고려하여 255자로 제한 (타 DB 마이그레이션 대비)
    # Rationale (Index):
    # 1. user_id: '내 즐겨찾기 목록 조회' API에서 WHERE 조건으로 빈번하게 사용됨.
    # 2. biz_item_id: 특정 합주실 상세 조회 시 '즐겨찾기 여부' 체크를 위해 복합 조회 또는 단일 조회가 일어남.
    user_id: str
    biz_item_id: str
    
    created_at: datetime
    updated_at: datetime

    # Rationale: Supabase 등 외부 ORM이나 딕셔너리 호환성을 위해 속성 접근 허용
    model_config = ConfigDict(from_attributes=True)
