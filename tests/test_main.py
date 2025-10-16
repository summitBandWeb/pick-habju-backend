from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_ping():
    # GET 요청 테스트
    response = client.get("/ping")
    assert response.status_code == 200
    assert response.json() == {"ok": True}


def test_post_item():
    response = client.post(
        "/items",
        json={"name": "Song"}
    )
    assert response.status_code == 200
    assert response.json().get("name") == "Song"
    assert response.json().get("id") == 1


def test_create_item():
    # POST 요청 테스트
    url = "/api/rooms/availability"
    payload = {
        "date": "2025-11-04",
        "hour_slots": ["18:00", "19:00", "20:00"],
        "rooms": [
            {
                "name": "블랙룸",
                "branch": "비쥬합주실 1호점",
                "business_id": "522011",
                "biz_item_id": "3968885"
            },
            {
                "name": "B룸",
                "branch": "비쥬합주실 2호점",
                "business_id": "706924",
                "biz_item_id": "4450073"
            },
        ]
    }

    response = client.post(
        url=url,
        json=payload,
    )
    assert response.status_code == 200
    assert response.json().get("date") == "2025-11-04"
    assert response.json().get("hour_slots") == ["18:00", "19:00", "20:00"]
    assert "available_biz_item_ids" in response.json()


def test_preflight_request():
    # CORS Preflight 요청 시뮬레이션
    habju = "https://www.pickhabju.com"
    url = "/api/rooms/availability"

    response = client.options(
        url=url,
        headers={
            "Origin": habju,  # 허용된 Origin 중 하나
            "Access-Control-Request-Method": "POST",  # 요청할 실제 메서드
            "Access-Control-Request-Headers": "Content-Type, Authorization",  # 요청할 사용자 정의 헤더
        }
    )

    # 1. 상태 코드 확인: Preflight 요청은 보통 200 OK를 반환합니다.
    assert response.status_code == 200

    # 2. 필수 응답 헤더 확인
    # 응답에 요청된 Origin이 포함된 Access-Control-Allow-Origin 헤더가 있는지 확인
    assert "access-control-allow-origin" in response.headers
    assert response.headers["access-control-allow-origin"] == habju

    # 요청된 메서드가 허용되는지 확인
    assert "access-control-allow-methods" in response.headers
    assert "POST" in response.headers["access-control-allow-methods"]

    # 요청된 헤더가 허용되는지 확인
    assert "access-control-allow-headers" in response.headers
    assert "content-type" in response.headers["access-control-allow-headers"].lower()
    assert "authorization" in response.headers["access-control-allow-headers"].lower()
