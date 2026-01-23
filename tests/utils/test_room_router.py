# te/test_room_router.py

from app.utils.room_router import filter_rooms_by_type
from app.models.dto import RoomDetail

def test_filter_rooms_by_type_print():
    rooms = [
        RoomDetail(name="D룸", branch="드림합주실 사당점", business_id="dream_sadang", biz_item_id="29", imageUrls=["img1.jpg"], maxCapacity=10, recommendCapacity=5, pricePerHour=15000, canReserveOneHour=True, requiresCallOnSameDay=False),
        RoomDetail(name="C룸", branch="드림합주실 사당점", business_id="dream_sadang", biz_item_id="28", imageUrls=["img2.jpg"], maxCapacity=8, recommendCapacity=4, pricePerHour=12000, canReserveOneHour=True, requiresCallOnSameDay=False),
        RoomDetail(name="B룸", branch="그루브 사당점", business_id="sadang", biz_item_id="groove-B", imageUrls=["img3.jpg"], maxCapacity=6, recommendCapacity=3, pricePerHour=10000, canReserveOneHour=True, requiresCallOnSameDay=False),
        RoomDetail(name="C룸", branch="그루브 사당점", business_id="sadang", biz_item_id="groove-C", imageUrls=["img4.jpg"], maxCapacity=4, recommendCapacity=2, pricePerHour=8000, canReserveOneHour=True, requiresCallOnSameDay=False),
        RoomDetail(name="Classic", branch="비쥬합주실 3호점", business_id="917236", biz_item_id="5098039", imageUrls=["img5.jpg"], maxCapacity=12, recommendCapacity=6, pricePerHour=20000, canReserveOneHour=True, requiresCallOnSameDay=False),
        RoomDetail(name="R룸", branch="준사운드 사당점", business_id="1384809", biz_item_id="6649826", imageUrls=["img6.jpg"], maxCapacity=10, recommendCapacity=5, pricePerHour=15000, canReserveOneHour=True, requiresCallOnSameDay=False),
    ]
    dream_rooms = filter_rooms_by_type(rooms, "dream")
    groove_rooms = filter_rooms_by_type(rooms, "groove")
    naver_rooms = filter_rooms_by_type(rooms, "naver")

    print("dream_rooms:", dream_rooms)
    print("groove_rooms:", groove_rooms)
    print("naver_rooms:", naver_rooms)

    # 아래는 실제 테스트 검증용 (필요시)
    assert all(r.branch == "드림합주실 사당점" for r in dream_rooms)
    assert all("그루브" in r.branch for r in groove_rooms)
    assert all("드림합주실" not in r.branch and "그루브" not in r.branch for r in naver_rooms)
