from fastapi import APIRouter, Depends, status, Query
from typing import Dict, Any, List
from app.repositories.base import IFavoriteRepository
from app.api.dependencies import get_favorite_repository, validate_device_id
from app.core.response import ApiResponse

router = APIRouter(
    prefix="/api/favorites",
    tags=["Favorites"],
    responses={404: {"description": "Not found"}},
)

@router.put("/{biz_item_id}", status_code=status.HTTP_200_OK, response_model=ApiResponse[Dict[str, bool]])
def add_favorite(
    biz_item_id: str,
    business_id: str = Query(..., description="합주실 지점 구별 ID"),
    x_device_id: str = Depends(validate_device_id),
    repo: IFavoriteRepository = Depends(get_favorite_repository)
) -> ApiResponse[Dict[str, bool]]:
    """
    즐겨찾기 추가
    
    - **biz_item_id**: 합주실 룸 구별 ID (Path Parameter)
    - **business_id**: 합주실 지점 구별 ID (Query Parameter)
    - **Header(X-Device-Id)**: 사용자 기기 식별 ID (UUID 형식 필수) - Dependency로 검증
    
    Returns:
        ApiResponse[Dict]: 성공 여부
    """
    repo.add(device_id=x_device_id, business_id=business_id, biz_item_id=biz_item_id)
    
    return ApiResponse.success(result={"added": True})

@router.delete("/{biz_item_id}", status_code=status.HTTP_200_OK, response_model=ApiResponse[Dict[str, bool]])
def delete_favorite(
    biz_item_id: str,
    business_id: str = Query(..., description="합주실 지점 구별 ID"),
    x_device_id: str = Depends(validate_device_id),
    repo: IFavoriteRepository = Depends(get_favorite_repository)
) -> ApiResponse[Dict[str, bool]]:
    """
    즐겨찾기 삭제
    
    - **biz_item_id**: 합주실 룸 구별 ID (Path Parameter)
    - **business_id**: 합주실 지점 구별 ID (Query Parameter)
    - **Header(X-Device-Id)**: 사용자 기기 식별 ID (UUID 형식 필수) - Dependency로 검증
    
    Returns:
        ApiResponse[Dict]: 삭제 성공 여부 (멱등성 보장)
    """
    repo.delete(device_id=x_device_id, business_id=business_id, biz_item_id=biz_item_id)
    return ApiResponse.success(result={"deleted": True})

@router.get("", status_code=status.HTTP_200_OK, response_model=ApiResponse[Dict[str, List[str]]])
def get_favorites(
    x_device_id: str = Depends(validate_device_id),
    repo: IFavoriteRepository = Depends(get_favorite_repository)
) -> ApiResponse[Dict[str, List[str]]]:
    """
    즐겨찾기 목록 조회
    
    - **Header(X-Device-Id)**: 사용자 기기 식별 ID (UUID 형식 필수) - Dependency로 검증
    
    Returns:
        ApiResponse[Dict]: {biz_item_ids: [id1, id2, ...]}
    """
    items = repo.get_all(device_id=x_device_id)
    return ApiResponse.success(result={"biz_item_ids": items})
