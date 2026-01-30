from fastapi import APIRouter, Depends, status, Query
from typing import Dict, Any, List
from app.repositories.base import IFavoriteRepository
from app.api.dependencies import get_favorite_repository, validate_device_id

from app.core.response import ApiResponse, success_response

router = APIRouter(
    prefix="/api/favorites",
    tags=["Favorites"],
    responses={404: {"description": "Not found"}},
)

@router.put("/{biz_item_id}", response_model=ApiResponse[Dict[str, bool]], status_code=status.HTTP_200_OK)
def add_favorite(
    biz_item_id: str,
    business_id: str = Query(..., description="합주실 지점 구별 ID"),
    x_device_id: str = Depends(validate_device_id),
    repo: IFavoriteRepository = Depends(get_favorite_repository)
):
    """
    즐겨찾기 추가
    
    - **biz_item_id**: 합주실 룸 구별 ID (Path Parameter)
    - **business_id**: 합주실 지점 구별 ID (Query Parameter)
    - **Header(X-Device-Id)**: 사용자 기기 식별 ID (UUID 형식 필수) - Dependency로 검증
    
    Returns:
        ApiResponse: 성공 여부 (Envelope Pattern)
    """
    repo.add(device_id=x_device_id, business_id=business_id, biz_item_id=biz_item_id)
    
    return success_response({"success": True})

@router.delete("/{biz_item_id}", response_model=ApiResponse[Dict[str, bool]], status_code=status.HTTP_200_OK)
def delete_favorite(
    biz_item_id: str,
    business_id: str = Query(..., description="합주실 지점 구별 ID"),
    x_device_id: str = Depends(validate_device_id),
    repo: IFavoriteRepository = Depends(get_favorite_repository)
):
    """
    즐겨찾기 삭제
    
    - **biz_item_id**: 합주실 룸 구별 ID (Path Parameter)
    - **business_id**: 합주실 지점 구별 ID (Query Parameter)
    - **Header(X-Device-Id)**: 사용자 기기 식별 ID (UUID 형식 필수) - Dependency로 검증
    
    Returns:
        ApiResponse: 성공 여부 (Envelope Pattern)
    """
    repo.delete(device_id=x_device_id, business_id=business_id, biz_item_id=biz_item_id)
    return success_response({"success": True})

@router.get("", response_model=ApiResponse[Dict[str, List[str]]], status_code=status.HTTP_200_OK)
def get_favorites(
    x_device_id: str = Depends(validate_device_id),
    repo: IFavoriteRepository = Depends(get_favorite_repository)
):
    """
    즐겨찾기 목록 조회
    
    - **Header(X-Device-Id)**: 사용자 기기 식별 ID (UUID 형식 필수) - Dependency로 검증
    
    Returns:
        ApiResponse: 즐겨찾기 목록 (Envelope Pattern)
    """
    items = repo.get_all(device_id=x_device_id)
    return success_response({"biz_item_ids": items})
