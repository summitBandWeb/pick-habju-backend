"""
가격 계산 도메인 서비스 (PricingService)

역할:
    - price_config(JSONB)를 파싱하여 시간대/요일/시즌별 단가를 결정
    - Split-and-Sum: 이용 시간을 1시간 슬롯으로 쪼개서 각각 단가를 계산 후 합산
    - 인원 초과 요금(extraCharge) 계산

Rationale:
    [질문 1] '추가요금 기준인원(baseCapacity)'과 '최소인원'이 다른 경우
    -> PricingService는 오직 '과금'만 담당합니다.
       baseCapacity를 초과하면 extraCharge를 부과하고,
       '최소인원 미달 → 예약 불가' 판단은 AvailabilityService(Phase 3)가 담당합니다.

    [질문 2] 시간대별 가격이 다른 경우
    -> Split-and-Sum 방식으로 해결합니다.
       17~19시 예약 시, 17시 슬롯과 18시 슬롯을 각각 price_config에 매칭하여
       서로 다른 단가를 적용한 뒤 합산합니다.

실행: pytest tests/services/test_pricing_service.py -v
"""

from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
from pydantic import BaseModel, Field, model_validator
import math


class TimeBand(BaseModel):
    """시간대 범위 (startHour 이상 ~ endHour 미만)

    Rationale:
        에이타입사운드 라운지점처럼 18~24시에만 가격이 다른 케이스를 수용하기 위함.
    """
    start_hour: int = Field(..., ge=0, le=24, alias="startHour")
    end_hour: int = Field(..., ge=0, le=24, alias="endHour")

    model_config = {"populate_by_name": True}

    @model_validator(mode="after")
    def validate_end_hour(self):
        """
        Validate that `end_hour` is strictly greater than `start_hour` and return the instance.
        
        Raises:
            ValueError: If `end_hour` is less than or equal to `start_hour`.
        
        Returns:
            self (TimeBand): The validated TimeBand instance.
        """
        if self.end_hour <= self.start_hour:
            raise ValueError("end_hour must be greater than start_hour")
        return self


class PriceRule(BaseModel):
    """price_config 내 개별 가격 규칙

    Rationale:
        노션에서 확정된 price_config 스키마를 반영합니다.
        season/days/time_band가 모두 null이면 '기본가' 규칙입니다.
        리스트 내에서 앞쪽에 위치할수록 우선순위가 높은 First-Match 방식을 사용합니다.

    Examples:
        기본가:        {"price": 10000}
        주말:          {"days": [5, 6], "price": 15000}
        저녁 피크:     {"timeBand": {"startHour": 18, "endHour": 24}, "price": 20000}
        성수기+주말:   {"season": "Summer", "days": [5, 6], "price": 25000}
    """
    season: Optional[str] = None
    days: Optional[List[int]] = None
    time_band: Optional[TimeBand] = Field(None, alias="timeBand")
    price: int

    model_config = {"populate_by_name": True}


class PricingService:
    """합주실 가격 계산 도메인 서비스"""

    def calculate_total_price(
        self,
        base_price: int,
        price_config: List[Dict[str, Any]],
        base_capacity: Optional[int],
        extra_charge: Optional[int],
        start_dt: datetime,
        end_dt: datetime,
        people_count: int,
    ) -> int:
        """
        Calculate the total charge for a booking using split-and-sum hourly pricing and optional per-person extra charges.
        
        Parameters:
            base_price (int): Fallback hourly price used when no pricing rule matches.
            price_config (List[Dict[str, Any]]): Raw price rule objects (JSONB-like) to be parsed and matched in priority order.
            base_capacity (Optional[int]): Number of people included in base price; if `None`, no per-person extra charges apply.
            extra_charge (Optional[int]): Additional charge per extra person per hour; if `None`, no per-person extra charges apply.
            start_dt (datetime): Booking start timestamp.
            end_dt (datetime): Booking end timestamp.
            people_count (int): Total number of people for the booking.
        
        Returns:
            int: Total price for the interval, expressed in the same integer currency units as the input prices.
        
        Raises:
            ValueError: If `start_dt` is not before `end_dt`.
        """
        if start_dt >= end_dt:
            raise ValueError("start_dt must be before end_dt")

        # 1. price_config 파싱
        rules = self._parse_rules(price_config)

        # 2. Split & Sum: 1시간 슬롯별 단가 합산
        total_base = 0
        slot = start_dt
        while slot < end_dt:
            unit = self._match_price(base_price, rules, slot)
            total_base += unit
            slot += timedelta(hours=1)

        # 3. 인원 추가 요금
        extra = self._calc_extra_charge(
            base_capacity, extra_charge, people_count, start_dt, end_dt
        )

        return total_base + extra

    # ==================== Private Methods ====================

    def _parse_rules(self, raw: List[Dict[str, Any]]) -> List[PriceRule]:
        """
        Parse raw price configuration dictionaries into a list of validated PriceRule objects.
        
        Parameters:
            raw (List[Dict[str, Any]]): Raw price configuration (JSON-like list of dicts) where each dict follows the PriceRule schema.
        
        Returns:
            List[PriceRule]: A list of PriceRule instances constructed from the input dictionaries.
        """
        return [PriceRule(**cfg) for cfg in raw]

    def _match_price(
        self, base_price: int, rules: List[PriceRule], target: datetime
    ) -> int:
        """
        Selects the unit price applicable at a given timestamp using first-match rule evaluation.
        
        Evaluates the provided rules in order and returns the price of the first rule whose day and time band match the timestamp. Season-based rules are ignored by this implementation. If no rule matches, returns the provided base_price.
        
        Returns:
            int: The matched rule's price, or `base_price` if no rule applies.
        """
        day = target.weekday()  # 0=Mon, 6=Sun
        hour = target.hour

        for rule in rules:
            # 시즌 체크 (현재 미구현 → 시즌 규칙은 스킵)
            # TODO: SeasonService 연동 후 활성화
            if rule.season is not None:
                continue

            # 요일 체크
            if rule.days is not None and day not in rule.days:
                continue

            # 시간대 체크
            if rule.time_band is not None:
                if not (rule.time_band.start_hour <= hour < rule.time_band.end_hour):
                    continue

            return rule.price

        return base_price

    def _calc_extra_charge(
        self,
        base_capacity: Optional[int],
        extra_charge: Optional[int],
        people: int,
        start: datetime,
        end: datetime,
    ) -> int:
        """
        Calculate extra charge for attendees exceeding the base capacity.
        
        Charges are applied only when both `base_capacity` and `extra_charge` are provided. The number of exceeded attendees is max(0, people - base_capacity). The duration is computed in hours and rounded up to the nearest whole hour; the total extra charge is exceeded * extra_charge * hours.
        
        Parameters:
            base_capacity (Optional[int]): Configured base capacity; if None, no extra charge is applied.
            extra_charge (Optional[int]): Charge per extra person per hour; if None, no extra charge is applied.
            people (int): Total number of attendees for the booking.
            start (datetime): Booking start time.
            end (datetime): Booking end time.
        
        Returns:
            int: Total extra charge (0 if none).
        """
        if base_capacity is None or extra_charge is None:
            return 0

        exceeded = max(0, people - base_capacity)
        hours = math.ceil((end - start).total_seconds() / 3600)
        return exceeded * extra_charge * hours