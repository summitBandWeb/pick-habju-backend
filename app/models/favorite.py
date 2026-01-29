from pydantic import BaseModel, ConfigDict, Field
from datetime import datetime

class Favorite(BaseModel):
    """사용자의 즐겨찾기 정보를 저장하는 데이터 모델 (Pydantic)

    Args:
        device_id (str): 사용자 기기 식별값 (UUID). Supabase DB 컬럼명과 일치.
        business_id (str): 합주실 지점 구별 ID (예: 'dream_sadang').
        biz_item_id (str): 합주실 룸 구별 ID (외부 크롤링 소스의 고유 ID).
        created_at (datetime | None): 즐겨찾기 최초 생성 일시. (DB 자동 생성 시 None 가능)

    Rationale:
        Supabase 스키마와 1:1 매핑되는 Pydantic 모델입니다.
        - user_id -> device_id 로 변경 (DB 컬럼명 준수)
        - business_id 필드 추가 (DB 컬럼 추가 반영)
        - id 필드 제거 (Composite Key 사용으로 인해 불필요하거나, DB 자동 생성)
    """
    
    # Rationale (Index):
    # device_id: '내 즐겨찾기 목록 조회' API에서 WHERE 조건으로 사용됨.
    device_id: str = Field(..., description="사용자 기기 식별값 (UUID)")
    
    # FK or Grouping key
    business_id: str = Field(..., description="합주실 지점 구별 ID")
    
    # Unique Item ID
    biz_item_id: str = Field(..., description="합주실 룸 구별 ID")
    
    created_at: datetime | None = Field(default=None, description="생성 일시")

    # Rationale: Supabase 등 외부 ORM이나 딕셔너리 호환성을 위해 속성 접근 허용
    model_config = ConfigDict(from_attributes=True)
