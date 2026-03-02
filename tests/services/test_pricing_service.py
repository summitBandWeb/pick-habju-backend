"""
PricingService 단위 테스트

테스트 대상:
- 기본 가격 계산 (config 없음)
- 요일별 가격 적용 (주말/평일)
- 시간대별 가격 (Split & Sum 검증)
- 인원 추가 요금 (baseCapacity 초과)
- 복합 케이스 (요일 + 시간대 + 추가인원)

실행: pytest tests/services/test_pricing_service.py -v
"""
import pytest
from unittest.mock import patch
from datetime import datetime
from app.services.pricing_service import PricingService


@pytest.fixture
def svc():
    return PricingService()


class TestBasicPrice:
    """config 없이 기본가만으로 계산"""

    def test_2hours_no_config(self, svc):
        """config 비어있으면 base_price * 시간"""
        price = svc.calculate_total_price(
            base_price=10000,
            price_config=[],
            base_capacity=None,
            extra_charge=None,
            start_dt=datetime(2025, 10, 6, 10, 0),  # 월요일
            end_dt=datetime(2025, 10, 6, 12, 0),
            people_count=3,
        )
        assert price == 20000  # 10000 * 2h

    def test_1hour(self, svc):
        """1시간 예약"""
        price = svc.calculate_total_price(
            base_price=15000,
            price_config=[],
            base_capacity=None,
            extra_charge=None,
            start_dt=datetime(2025, 10, 6, 14, 0),
            end_dt=datetime(2025, 10, 6, 15, 0),
            people_count=2,
        )
        assert price == 15000

    def test_invalid_time_range(self, svc):
        """시작 >= 종료이면 ValueError"""
        with pytest.raises(ValueError):
            svc.calculate_total_price(
                10000, [], None, None,
                datetime(2025, 10, 6, 12, 0),
                datetime(2025, 10, 6, 10, 0),
                2,
            )


class TestDayPricing:
    """요일별 가격 적용"""

    def test_weekend_price(self, svc):
        """토요일이면 주말 가격 적용"""
        config = [{"week": [5, 6], "price": 20000}]
        price = svc.calculate_total_price(
            base_price=10000,
            price_config=config,
            base_capacity=None,
            extra_charge=None,
            start_dt=datetime(2025, 10, 11, 10, 0),  # 토요일
            end_dt=datetime(2025, 10, 11, 12, 0),
            people_count=3,
        )
        assert price == 40000  # 20000 * 2h

    def test_weekday_fallback(self, svc):
        """평일이면 주말 config 미매칭 -> base_price"""
        config = [{"week": [5, 6], "price": 20000}]
        price = svc.calculate_total_price(
            base_price=10000,
            price_config=config,
            base_capacity=None,
            extra_charge=None,
            start_dt=datetime(2025, 10, 6, 10, 0),  # 월요일
            end_dt=datetime(2025, 10, 6, 12, 0),
            people_count=3,
        )
        assert price == 20000  # 10000 * 2h (기본가)


class TestTimeBandPricing:
    """시간대별 가격 (Split & Sum 핵심 검증)"""

    def test_peak_evening(self, svc):
        """18~24시 피크 가격, 17~19시 예약 -> 1슬롯 기본 + 1슬롯 피크"""
        config = [
            {"timeBand": {"startHour": 18, "endHour": 24}, "price": 20000},
        ]
        price = svc.calculate_total_price(
            base_price=10000,
            price_config=config,
            base_capacity=None,
            extra_charge=None,
            start_dt=datetime(2025, 10, 6, 17, 0),
            end_dt=datetime(2025, 10, 6, 19, 0),
            people_count=3,
        )
        # 17~18: base 10000, 18~19: peak 20000
        assert price == 30000

    def test_full_peak(self, svc):
        """전체 시간이 피크 구간에 포함"""
        config = [
            {"timeBand": {"startHour": 18, "endHour": 24}, "price": 20000},
        ]
        price = svc.calculate_total_price(
            base_price=10000,
            price_config=config,
            base_capacity=None,
            extra_charge=None,
            start_dt=datetime(2025, 10, 6, 19, 0),
            end_dt=datetime(2025, 10, 6, 21, 0),
            people_count=3,
        )
        assert price == 40000  # 20000 * 2h


class TestExtraCharge:
    """인원 추가 요금"""

    def test_exceeded_people(self, svc):
        """기준 4명, 6명 이용 -> 2명 초과 * 추가금"""
        price = svc.calculate_total_price(
            base_price=10000,
            price_config=[],
            base_capacity=4,
            extra_charge=5000,
            start_dt=datetime(2025, 10, 6, 10, 0),
            end_dt=datetime(2025, 10, 6, 12, 0),
            people_count=6,
        )
        # 기본: 10000*2 = 20000
        # 추가: 2명 * 5000 * 2h = 20000
        assert price == 40000

    def test_no_exceed(self, svc):
        """기준 이하 인원이면 추가 요금 없음"""
        price = svc.calculate_total_price(
            base_price=10000,
            price_config=[],
            base_capacity=6,
            extra_charge=5000,
            start_dt=datetime(2025, 10, 6, 10, 0),
            end_dt=datetime(2025, 10, 6, 12, 0),
            people_count=4,
        )
        assert price == 20000  # 추가 요금 없음

    def test_no_extra_charge_field(self, svc):
        """extraCharge가 None이면 추가 요금 미적용"""
        price = svc.calculate_total_price(
            base_price=10000,
            price_config=[],
            base_capacity=4,
            extra_charge=None,
            start_dt=datetime(2025, 10, 6, 10, 0),
            end_dt=datetime(2025, 10, 6, 12, 0),
            people_count=10,
        )
        assert price == 20000


class TestComplexCase:
    """복합 시나리오"""

    def test_weekend_peak_with_extra(self, svc):
        """토요일 + 피크 시간대 + 인원 초과"""
        config = [
            # 주말 + 피크: 가장 구체적 -> 우선
            {"week": [5, 6], "timeBand": {"startHour": 18, "endHour": 24}, "price": 25000},
            # 주말 전체
            {"week": [5, 6], "price": 18000},
        ]
        # 토요일 17~19시, 6명(기준4명, 추가 5000원)
        price = svc.calculate_total_price(
            base_price=10000,
            price_config=config,
            base_capacity=4,
            extra_charge=5000,
            start_dt=datetime(2025, 10, 11, 17, 0),  # 토요일
            end_dt=datetime(2025, 10, 11, 19, 0),
            people_count=6,
        )
        # 17~18: 주말 전체 매칭 -> 18000
        # 18~19: 주말+피크 매칭 -> 25000
        # 기본 합계: 43000
        # 추가: 2명 * 5000 * 2h = 20000
        assert price == 63000


class TestSeasonPricing:
    """시즌 가격 적용 (A안: 크롤링 수집 season 태그는 활성으로 간주)"""

    @patch.object(PricingService, '_is_season_active', return_value=True)
    def test_season_rule_applied_on_match(self, mock_is_active, svc):
        """season 룰이 있어도 week 조건을 만족해야 적용됨"""
        config = [
            {"season": "Summer", "week": [5, 6], "price": 25000},
            {"price": 10000},  # 기본가
        ]
        # 토요일 -> season+주말 룰 매칭
        price = svc.calculate_total_price(
            base_price=10000,
            price_config=config,
            base_capacity=None,
            extra_charge=None,
            start_dt=datetime(2025, 10, 11, 14, 0),  # 토요일
            end_dt=datetime(2025, 10, 11, 16, 0),
            people_count=3,
        )
        assert price == 50000  # 25000 * 2h

    @patch.object(PricingService, '_is_season_active', return_value=True)
    def test_season_rule_weekday_fallback(self, mock_is_active, svc):
        """season 룰이 있어도 week 조건 불일치 시 기본가 적용"""
        config = [
            {"season": "Summer", "week": [5, 6], "price": 25000},
            {"price": 10000},  # 기본가
        ]
        # 월요일 -> season+주말 미매칭 -> 기본가
        price = svc.calculate_total_price(
            base_price=10000,
            price_config=config,
            base_capacity=None,
            extra_charge=None,
            start_dt=datetime(2025, 10, 6, 14, 0),  # 월요일
            end_dt=datetime(2025, 10, 6, 16, 0),
            people_count=3,
        )
        assert price == 20000  # 10000 * 2h (기본가)

    @patch.object(PricingService, '_is_season_active', return_value=True)
    def test_season_only_rule_always_applied(self, mock_is_active, svc):
        """week/timeBand 없는 season 룰은 모든 시간대에 적용됨 (A안 핵심)"""
        config = [
            {"season": "개강특가", "price": 12000},
            {"price": 10000},  # 기본가
        ]
        # 평일이라도 season 룰이 week 조건 없으면 무조건 매칭
        price = svc.calculate_total_price(
            base_price=10000,
            price_config=config,
            base_capacity=None,
            extra_charge=None,
            start_dt=datetime(2025, 10, 6, 14, 0),  # 월요일
            end_dt=datetime(2025, 10, 6, 16, 0),
            people_count=3,
        )
        assert price == 24000  # 12000 * 2h
