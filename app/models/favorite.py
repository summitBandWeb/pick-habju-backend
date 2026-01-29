from pydantic import BaseModel, ConfigDict
from datetime import datetime

class Favorite(BaseModel):
    """
    사용자의 즐겨찾기 정보를 담는 데이터 모델 (Pydantic)
    """
    id: int
    user_id: str
    biz_item_id: str
    created_at: datetime
    updated_at: datetime
    
    # Rationale: Supabase 등 외부 ORM이나 딕셔너리 호환성을 위해 속성 접근 허용
    model_config = ConfigDict(from_attributes=True)
