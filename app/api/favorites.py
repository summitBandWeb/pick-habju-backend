from fastapi import APIRouter, Depends, Header, HTTPException, status
from app.repositories.base import IFavoriteRepository
from app.api.dependencies import get_favorite_repository

router = APIRouter(
    prefix="/api/favorites",
    tags=["Favorites"],
    responses={404: {"description": "Not found"}},
)

@router.put("/{biz_item_id}", status_code=status.HTTP_201_CREATED)
def add_favorite(
    biz_item_id: str,
    x_device_id: str = Header(..., alias="X-Device-Id"),
    repo: IFavoriteRepository = Depends(get_favorite_repository)
):
    """
    즐겨찾기 추가
    
    - **biz_item_id**: 합주실 고유 ID
    - **Header(X-Device-Id)**: 사용자 기기 식별 ID
    
    Returns:
        201 Created: 신규 추가됨
        200 OK: 이미 존재함
    """
    if not x_device_id:
         raise HTTPException(status_code=400, detail="X-Device-Id header missing")

    is_created = repo.add(user_id=x_device_id, biz_item_id=biz_item_id)
    
    if not is_created:
        # 이미 존재하면 200 OK 반환 (FastAPI는 기본적으로 반환값이 없으면 200/201 등 설정된 status_code를 따라감)
        # 멱등성을 위해 200으로 명시적 응답
        from fastapi import Response
        return Response(status_code=status.HTTP_200_OK)
    
    return {"status": "created", "biz_item_id": biz_item_id}

@router.delete("/{biz_item_id}", status_code=status.HTTP_200_OK)
def delete_favorite(
    biz_item_id: str,
    x_device_id: str = Header(..., alias="X-Device-Id"),
    repo: IFavoriteRepository = Depends(get_favorite_repository)
):
    """
    즐겨찾기 삭제
    
    - **biz_item_id**: 합주실 고유 ID
    - **Header(X-Device-Id)**: 사용자 기기 식별 ID
    
    Returns:
        200 OK: 삭제 성공 또는 이미 없음 (멱등성 보장)
    """
    if not x_device_id:
         raise HTTPException(status_code=400, detail="X-Device-Id header missing")
         
    repo.delete(user_id=x_device_id, biz_item_id=biz_item_id)
    return {"status": "deleted"}
