from fastapi import APIRouter, Depends, Header, HTTPException, status, Response, Query
from typing import Dict, Any, List
import uuid
from app.repositories.base import IFavoriteRepository
from app.api.dependencies import get_favorite_repository

router = APIRouter(
    prefix="/api/favorites",
    tags=["Favorites"],
    responses={404: {"description": "Not found"}},
)

def validate_uuid(value: str):
    try:
        uuid.UUID(value)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid X-Device-Id format")

@router.put("/{biz_item_id}", status_code=status.HTTP_200_OK)
def add_favorite(
    biz_item_id: str,
    business_id: str = Query(..., description="합주실 지점 구별 ID"),
    x_device_id: str | None = Header(default=None, alias="X-Device-Id"),
    repo: IFavoriteRepository = Depends(get_favorite_repository)
) -> Dict[str, Any]:
    """
    즐겨찾기 추가
    
    - **biz_item_id**: 합주실 룸 구별 ID (Path Parameter)
    - **business_id**: 합주실 지점 구별 ID (Query Parameter)
    - **Header(X-Device-Id)**: 사용자 기기 식별 ID (UUID 형식 필수)
    
    Returns:
        200 OK: 성공 (신규 추가 또는 이미 존재)
    """
    if not x_device_id or not x_device_id.strip():
         raise HTTPException(status_code=400, detail="X-Device-Id header is required and cannot be empty")
    
    validate_uuid(x_device_id)

    repo.add(device_id=x_device_id, business_id=business_id, biz_item_id=biz_item_id)
    
    return {"success": True}

@router.delete("/{biz_item_id}", status_code=status.HTTP_200_OK)
def delete_favorite(
    biz_item_id: str,
    business_id: str = Query(..., description="합주실 지점 구별 ID"),
    x_device_id: str | None = Header(default=None, alias="X-Device-Id"),
    repo: IFavoriteRepository = Depends(get_favorite_repository)
) -> Dict[str, Any]:
    """
    즐겨찾기 삭제
    
    - **biz_item_id**: 합주실 룸 구별 ID (Path Parameter)
    - **business_id**: 합주실 지점 구별 ID (Query Parameter)
    - **Header(X-Device-Id)**: 사용자 기기 식별 ID (UUID 형식 필수)
    
    Returns:
        200 OK: 삭제 성공 또는 이미 없음 (멱등성 보장)
    """
    if not x_device_id or not x_device_id.strip():
         raise HTTPException(status_code=400, detail="X-Device-Id header is required and cannot be empty")
    
    validate_uuid(x_device_id)
         
    repo.delete(device_id=x_device_id, business_id=business_id, biz_item_id=biz_item_id)
    return {"success": True}

@router.get("", status_code=status.HTTP_200_OK)
def get_favorites(
    x_device_id: str | None = Header(default=None, alias="X-Device-Id"),
    repo: IFavoriteRepository = Depends(get_favorite_repository)
) -> Dict[str, List[str]]:
    """
    즐겨찾기 목록 조회
    
    - **Header(X-Device-Id)**: 사용자 기기 식별 ID (UUID 형식 필수)
    
    Returns:
        200 OK: {"biz_item_ids": [id1, id2, ...]}
    """
    if not x_device_id or not x_device_id.strip():
         raise HTTPException(status_code=400, detail="X-Device-Id header is required and cannot be empty")
    
    validate_uuid(x_device_id)
    
    items = repo.get_all(device_id=x_device_id)
    return {"biz_item_ids": items}
