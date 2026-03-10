"""
애플리케이션 전역에서 사용되는 상수를 정의합니다.
"""

import math
from typing import Dict, List, Tuple

# 서비스 지역 지하철역 좌표 (위도, 경도)
SERVICE_AREA_STATIONS: Dict[str, Tuple[float, float]] = {
    "이수역": (37.4856, 126.9823),
    "사당역": (37.4766, 126.9816),
    "홍대입구역": (37.5571, 126.9236),
    "합정역": (37.5496, 126.9139),
    "신촌역": (37.5550, 126.9366),
    "상도역": (37.5028, 126.9532),
    "흑석역": (37.5084, 126.9631),
}

# 서비스 지역 반경 (km)
SERVICE_AREA_RADIUS_KM = 2.0

# 우선 수집 대상 역세권 검색 쿼리
PRIORITY_AREA_QUERIES = [
    "이수역 합주실",
    "사당역 합주실",
    "사당역 음악연습실",
    "흑석역 합주실",
    "상도역 합주실",
    "홍대입구역 합주실",
    "합정역 합주실",
    "신촌역 합주실",
]

# 서울 25개 자치구
SEOUL_DISTRICTS = [
    "강남구 합주실", "강동구 합주실", "강북구 합주실", "강서구 합주실", "관악구 합주실",
    "광진구 합주실", "구로구 합주실", "금천구 합주실", "노원구 합주실", "도봉구 합주실",
    "동대문구 합주실", "동작구 합주실", "마포구 합주실", "서대문구 합주실", "서초구 합주실",
    "성동구 합주실", "성북구 합주실", "송파구 합주실", "양천구 합주실", "영등포구 합주실",
    "용산구 합주실", "은평구 합주실", "종로구 합주실", "중구 합주실", "중랑구 합주실"
]

# 주요 광역시 및 수도권 도시
MAJOR_CITIES = [
    "부산 합주실", "대구 합주실", "인천 합주실", "광주 합주실", "대전 합주실", "울산 합주실",
    "수원 합주실", "성남 합주실", "고양 합주실", "부천 합주실"
]


def haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """두 좌표 간 거리를 km 단위로 반환한다 (Haversine 공식)."""
    R = 6371
    dlat = math.radians(lat2 - lat1)
    dlng = math.radians(lng2 - lng1)
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlng / 2) ** 2
    )
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def is_in_service_area(
    lat: float,
    lng: float,
    radius_km: float = SERVICE_AREA_RADIUS_KM,
) -> bool:
    """좌표가 서비스 지역(역 기준 반경) 내에 있는지 판별한다."""
    for _, (slat, slng) in SERVICE_AREA_STATIONS.items():
        if haversine_km(lat, lng, slat, slng) <= radius_km:
            return True
    return False
