"""tests/utils/test_room_loader.py

room_loader.get_rooms_by_criteria 의 필터링 로직을 검증하는 유닛 테스트.
"""
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.core.constants import MAX_EXCLUDED_PRICE_PER_HOUR
from app.utils import room_loader


# ────────────────────────── helpers ──────────────────────────

def _room_row(**overrides):
    """최소한의 유효한 DB room row dict를 반환하는 헬퍼.

    Args:
        **overrides: 기본값에서 덮어쓸 필드.

    Rationale:
        테스트마다 전체 row를 하드코딩하면 모델 스키마 변경 시 수정 범위가
        폭발적으로 늘어남. 기본값을 하나로 관리하여 유지보수 비용을 낮춤.
    """
    row = {
        "name": "A room",
        "business_id": "522011",
        "biz_item_id": "item-1",
        "image_urls": [],
        "max_capacity": 5,
        "recommend_capacity": 4,
        "price_config": None,
        "price_per_hour": 15000,
        "can_reserve_one_hour": True,
        "requires_call_on_sameday": False,
    }
    row.update(overrides)
    return row


@pytest.fixture()
def mock_supabase_query(monkeypatch):
    """Supabase 쿼리 체인 전체를 MagicMock으로 대체하는 픽스처.

    Rationale:
        DB 연결 없이 room_loader 내부 필터 로직만 독립적으로 검증하기 위해
        supabase 클라이언트를 모킹. 각 테스트가 `.execute.return_value`를
        설정하여 원하는 데이터를 주입할 수 있음.
    """
    mock_query = MagicMock()
    mock_query.select.return_value = mock_query
    mock_query.gte.return_value = mock_query
    mock_query.in_.return_value = mock_query

    mock_sb = MagicMock()
    mock_sb.table.return_value = mock_query
    monkeypatch.setattr(room_loader, "supabase", mock_sb)
    return mock_query


# ────────────────────── 기존 필터링 테스트 ──────────────────────

def test_get_rooms_by_criteria_keeps_room_when_branch_missing(mock_supabase_query):
    """branch 정보가 없는 룸은 fallback 처리되어 결과에 포함되어야 함."""
    missing_branch_row = _room_row(branch=None, image_urls=None)
    out_of_bound_row = _room_row(
        name="B room",
        biz_item_id="item-2",
        branch={"name": "Gangnam", "lat": 35.0, "lng": 129.0},
    )
    in_bound_row = _room_row(
        name="C room",
        biz_item_id="item-3",
        branch={"name": "Seoul", "lat": 37.5, "lng": 127.1},
    )
    mock_supabase_query.execute.return_value = SimpleNamespace(
        data=[missing_branch_row, out_of_bound_row, in_bound_row]
    )

    rooms = room_loader.get_rooms_by_criteria(
        capacity=3, swLat=37.0, swLng=127.0, neLat=38.0, neLng=128.0
    )

    assert len(rooms) == 2
    assert {r.biz_item_id for r in rooms} == {"item-1", "item-3"}
    missing_branch = next(r for r in rooms if r.biz_item_id == "item-1")
    assert missing_branch.branch == room_loader.RoomDetail.BRANCH_FALLBACK_NAME
    mock_supabase_query.in_.assert_called_once()


def test_get_rooms_by_criteria_can_disable_priority_filter(mock_supabase_query, monkeypatch):
    """PRIORITY_AREA_ONLY_FILTER=false 이면 business_id 필터 없이 조회해야 함."""
    row = _room_row(branch={"name": "Branch", "lat": 37.5, "lng": 127.1})
    mock_supabase_query.execute.return_value = SimpleNamespace(data=[row])
    monkeypatch.setenv("PRIORITY_AREA_ONLY_FILTER", "false")

    rooms = room_loader.get_rooms_by_criteria(capacity=1)

    assert len(rooms) == 1
    mock_supabase_query.in_.assert_not_called()


# ────────── price_per_hour 필터 (MAX_EXCLUDED_PRICE_PER_HOUR) 테스트 ──────────

class TestPriceFilter:
    """price_per_hour <= MAX_EXCLUDED_PRICE_PER_HOUR 룸 필터링 검증.

    Rationale:
        테스트값을 MAX_EXCLUDED_PRICE_PER_HOUR 기준 상대값(예: -1000, -1, +1)으로
        표현하여 상수 변경 시 테스트 코드 수정 없이 자동으로 반영되도록 설계함.
    """

    def test_price_well_below_threshold_is_excluded(self, mock_supabase_query):
        """임계치보다 한참 낮은 값(MAX - 1000)도 제외되어야 함."""
        rows = [
            _room_row(biz_item_id="item-ok",  price_per_hour=15000,
                      branch={"name": "B", "lat": 37.5, "lng": 127.1}),
            _room_row(biz_item_id="item-low", price_per_hour=MAX_EXCLUDED_PRICE_PER_HOUR - 1000,
                      branch={"name": "B", "lat": 37.5, "lng": 127.1}),
        ]
        mock_supabase_query.execute.return_value = SimpleNamespace(data=rows)

        rooms = room_loader.get_rooms_by_criteria(
            capacity=1, swLat=37.0, swLng=127.0, neLat=38.0, neLng=128.0
        )

        assert len(rooms) == 1
        assert rooms[0].biz_item_id == "item-ok"

    def test_price_at_threshold_is_excluded(self, mock_supabase_query):
        """임계치와 정확히 같은 값(MAX_EXCLUDED_PRICE_PER_HOUR)도 제외되어야 함 (이하 조건)."""
        rows = [
            _room_row(biz_item_id="item-ok",       price_per_hour=MAX_EXCLUDED_PRICE_PER_HOUR + 1,
                      branch={"name": "B", "lat": 37.5, "lng": 127.1}),
            _room_row(biz_item_id="item-boundary", price_per_hour=MAX_EXCLUDED_PRICE_PER_HOUR,
                      branch={"name": "B", "lat": 37.5, "lng": 127.1}),
        ]
        mock_supabase_query.execute.return_value = SimpleNamespace(data=rows)

        rooms = room_loader.get_rooms_by_criteria(
            capacity=1, swLat=37.0, swLng=127.0, neLat=38.0, neLng=128.0
        )

        assert len(rooms) == 1
        assert rooms[0].biz_item_id == "item-ok"

    def test_price_zero_is_excluded(self, mock_supabase_query):
        """price_per_hour=0 (공지 전용 탭 오수집 케이스)도 제외되어야 함."""
        rows = [
            _room_row(biz_item_id="item-ok",   price_per_hour=15000,
                      branch={"name": "B", "lat": 37.5, "lng": 127.1}),
            _room_row(biz_item_id="item-zero", price_per_hour=0,
                      branch={"name": "B", "lat": 37.5, "lng": 127.1}),
        ]
        mock_supabase_query.execute.return_value = SimpleNamespace(data=rows)

        rooms = room_loader.get_rooms_by_criteria(
            capacity=1, swLat=37.0, swLng=127.0, neLat=38.0, neLng=128.0
        )

        assert len(rooms) == 1
        assert rooms[0].biz_item_id == "item-ok"

    def test_price_negative_is_excluded(self, mock_supabase_query):
        """price_per_hour=-1 (파싱 오류 케이스)도 제외되어야 함."""
        rows = [
            _room_row(biz_item_id="item-ok",  price_per_hour=15000,
                      branch={"name": "B", "lat": 37.5, "lng": 127.1}),
            _room_row(biz_item_id="item-neg", price_per_hour=-1,
                      branch={"name": "B", "lat": 37.5, "lng": 127.1}),
        ]
        mock_supabase_query.execute.return_value = SimpleNamespace(data=rows)

        rooms = room_loader.get_rooms_by_criteria(
            capacity=1, swLat=37.0, swLng=127.0, neLat=38.0, neLng=128.0
        )

        assert len(rooms) == 1
        assert rooms[0].biz_item_id == "item-ok"

    def test_price_just_above_threshold_is_included(self, mock_supabase_query):
        """임계치보다 1원 높은 룸(MAX + 1)은 반드시 포함되어야 함."""
        rows = [
            _room_row(biz_item_id="item-pass", price_per_hour=MAX_EXCLUDED_PRICE_PER_HOUR + 1,
                      branch={"name": "B", "lat": 37.5, "lng": 127.1}),
        ]
        mock_supabase_query.execute.return_value = SimpleNamespace(data=rows)

        rooms = room_loader.get_rooms_by_criteria(
            capacity=1, swLat=37.0, swLng=127.0, neLat=38.0, neLng=128.0
        )

        assert len(rooms) == 1
        assert rooms[0].biz_item_id == "item-pass"

    def test_logs_warning_when_excluded(self, mock_supabase_query, caplog):
        """필터 제거 시 warning 로그 및 상세 메시지가 남아야 함 (운영 가시성 보장)."""
        import logging
        excluded_price = MAX_EXCLUDED_PRICE_PER_HOUR - 1000
        rows = [
            _room_row(biz_item_id="item-low", price_per_hour=excluded_price,
                      branch={"name": "B", "lat": 37.5, "lng": 127.1}),
        ]
        mock_supabase_query.execute.return_value = SimpleNamespace(data=rows)

        with caplog.at_level(logging.WARNING, logger="app.utils.room_loader"):
            room_loader.get_rooms_by_criteria(
                capacity=1, swLat=37.0, swLng=127.0, neLat=38.0, neLng=128.0
            )

        assert any(
            r.levelno == logging.WARNING and
            "price_too_low" in r.message and
            str(excluded_price) in r.message
            for r in caplog.records
        )
