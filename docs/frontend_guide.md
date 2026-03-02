# 프론트엔드 연동 가이드 (Metadata V2)

본 문서는 합주실 예약 시스템의 메타데이터 품질 향상 버전(v2.0)에 맞춰 프론트엔드에서 연동해야 할 API 응답 구조 및 UI 처리 가이드입니다.

## 1. 구현 가이드 (Frontend Action Items)

백엔드 배포 단계에 따라 프론트엔드 대응 전략이 나뉩니다.

### 1-1. 현재 브랜치 머지 직후 (v2.0.0-alpha)
**즉시 적용 가능한 UI 변경 사항입니다.**

1.  **인원 표기 (Capacity Range):**
    *   `recommend_capacity_range` 배열(`[min, max]`)이 존재하면 **"2~6명"** 형태로 우선 표기해 주세요.
    *   없으면 기존대로 `~4명` 또는 `최대 6명` 표기 (Legacy 호환).
2.  **정책 경고 (Policy Warnings) 표시:**
    *   `policy_warnings` 배열 내 객체의 `type`을 확인하여, 사용자가 예약을 클릭했을 때 또는 룸 리스트 렌더링 시 알맞은 가이드를 제공해야 합니다.
    *   **type 목록:**
        *   `call_required_1h` (1시간 예약 시 전화 문의 필요)
        *   `chat_required_1h` (1시간 예약 시 채팅/톡톡 문의 필요)
        *   `call_required_today` (당일 예약 시 전화 문의 필요)

### 1-2. 백엔드 추가 구현 배포 시 (v2.0.1-beta 예정)
**백엔드에서 데이터 정제(Data Backfilling) 및 가격 정책(Price Config) 파싱 로직이 배포된 후 대응이 필요한 사항입니다.**

1.  **동적 가격 (Dynamic Price):**
    *   사용자가 날짜/시간/인원을 선택할 때마다 API를 재호출하여 `estimated_price`를 확인합니다.
    *   `estimated_price`가 `null`이 아니면 이를 **최종 결제 예정 금액**으로 표시합니다.
    *   `null`인 경우(Legacy 데이터)에는 기존 로직(`pricePerHour * 시간`)으로 계산하여 표시합니다.
2.  **문의 필요 상태 (Capacity Check):**
    *   `maxCapacity`가 `0` 또는 `null`로 내려오는 경우(기존엔 100), **"문의 필요"** 버튼으로 전환하거나 예약을 막고 전화 연결을 유도해야 합니다.


---

# (부록) 합주실 메타데이터 알고리즘 v2.0 기술 문서 (Original)

본 문서는 합주실 예약 시스템의 메타데이터 품질 향상 및 동적 가격/예약 정책 적용을 위한 v2.0 알고리즘의 상세 명세입니다.

## 1. 프로젝트 개요

*   **목표:** 고도화된 메타데이터(동적 가격, 정책, 범위 기반 인원)를 통해 정확한 예약 정보를 제공하고 사용자 경험을 개선합니다.
*   **주요 변경:**
    *   고정 가격 → **동적 가격 계산** (시간/요일/인원별 변동)
    *   단순 가용성 → **정책 기반 필터링** (최소 시간, 당일 예약 제한 등)
    *   단일 인원(최대) → **권장 인원 범위** (`min` ~ `max`) 제공

## 2. 상세 구현 내용

### Phase 1: DB 스키마 및 데이터 구조 (V2 Fields)

DTO(`RoomDetail`)에 다음 필드들이 추가되거나 의미가 확장되었습니다.

| 필드명 | 타입 | 설명 | 비고 (V2) |
| :--- | :--- | :--- | :--- |
| `recommend_capacity_range` | `List[int]` | 권장 인원 범위 `[min, max]` | **[NEW]** 기존 `recommendCapacity`(int)와 공존 |
| `base_capacity` | `int` | 기본 인원 | **[NEW]** 초과 시 추가 요금 발생 기준 |
| `extra_charge` | `int` | 인원 추가 요금 (1인당/시간당) | **[NEW]** |
| `price_config` | `JSON` | 요일/시간대별 가격 정책 | **[NEW]** 서버 내부 계산용 |

### Phase 2: 가격 계산 엔진 (Pricing Logic)

서버에서 예약 요청(`날짜`, `시간`, `인원`)에 따라 예상 가격(`estimated_price`)을 계산하여 반환합니다.

1.  **Split & Sum 알고리즘:**
    *   예약 시간이 여러 가격 구간에 걸칠 경우 1시간 단위로 분리하여 계산 후 합산합니다.
    *   *예: 평일 17시~19시 예약 (17시: 일반 요금 / 18시: 피크 요금) → `(17시 요금) + (18시 요금)`*
2.  **인원 추가 요금 자동 계산:**
    *   예약 인원 > `base_capacity`인 경우: `(초과 인원 * extra_charge * 예약 시간)`이 가산됩니다.

### Phase 3: 예약 정책 및 가용성 (Policy Checker)

`AvailabilityService` 응답에 정책 위반 경고(`policy_warnings`)가 포함될 수 있습니다.

*   **1시간 예약 제한 (`canReserveOneHour=False`)**: 1시간만 선택 시 경고 메시지 반환.
*   **당일 예약 제한 (`requiresCallOnSameDay=True`)**: 당일 예약 시도 시 "전화 문의 필요" 경고 반환.

### Phase 4: API 응답 정규화 (Response Structure, v2.0.0-beta)

API 응답(`AvailabilityResponse`)의 전체 구조는 다음과 같습니다. 프론트엔드의 매핑 연산 비용 절감을 위해 **지점(Branch) 하위로 룸이 그룹핑된 계층형 구조**로 개편되었습니다. 기존의 플랫한 `results`와 독립적인 `branch_summary`는 폐기되었습니다.

```json
{
  "date": "2024-05-20",
  "start_hour": "17:00",
  "end_hour": "19:00",
  "available_biz_item_ids": [
    "5979448",
    "5979471"
  ],
  "hour_slots": [
    "17:00",
    "18:00"
  ],
  "branches": [
    {
      "business_id": "1182602",
      "branch": "그라운드합주실 신촌1호점",
      "lat": 37.556,
      "lng": 126.937,
      "min_price_available": 12000,
      "min_price_partial": null,
      "available_count": 2,
      "rooms": [
        {
          "biz_item_id": "5979448",
          "name": "A룸",
          "available": "unknown",         // true / false / "unknown"
          "available_slots": {
            "17:00": false,
            "18:00": false
          },
          "price_per_hour": 15000,
          "estimated_price": null,        // [NEW] 계산된 최종 예상 금액 (unknown일 경우 null)
          "image_urls": [
            "https://example.com/image1.jpg"
          ],
          "max_capacity": 6,
          "recommend_capacity": 4,        // [Legacy] 하위 호환성 유지 (추후 제거)
          "recommend_capacity_range": [2, 6], // [NEW] 권장 인원 범위
          "base_capacity": 4,             // [NEW]
          "extra_charge": 5000,           // [NEW]
          "min_capacity": 1,              // [NEW] 최소 예약 인원
          "min_hours": 1,                 // [NEW] 최소 예약 시간
          "max_hours": 5,                 // [NEW] 거시적 최대 예약 허용 시간
          "standby_days": 1,              // [NEW] 오픈 예정 대기 일수 (1 = 내일 오픈 예약가능)
          "policy_warnings": [            // [NEW] 예약 시 주의/안내 사항 배열
            {
              "type": "call_required_today",
              "message": "당일 예약은 전화 문의가 필요합니다."
            }
          ]
        }
      ]
    }
  ]
}
```
### 4-1. `available` 필드 상태값 (Enum)
*   `true` (Boolean): 예약 가능 (요청한 전체 시간에 대해 빈 방)
*   `false` (Boolean): 예약 불가 (이미 예약됨)
*   `"unknown"` (String): **오픈 대기** (요청한 날짜가 아직 예약 오픈 기간이 아니거나 대기 중임. 예약 불가)

### 4-2. `min_price_available` 및 `min_price_partial` 필드 정책
두 필드의 키(key)는 결괏값에 **항상 포함**되며 조건부로 생략되지 않습니다.
값이 `null`이 되는 경우는 다음과 같습니다.

*   `min_price_available`: 결과 룸들 중 `available: true`인 방이 **하나도 없을 때** `null`이 됩니다. 예약 가능한 방이 하나라도 있으면 최소 가격(숫자)이 들어갑니다.
*   `min_price_partial`: 결과 룸들 중 `available: false` 이면서 슬롯 일부가 비어있는 방이 **하나도 없을 때** `null`이 됩니다. 부분 예약 가능한 방이 하나라도 있으면 가장 길게 연속된 예약가능 시간 기준의 최소 가격(숫자)이 들어갑니다. (오픈 대기인 `"unknown"` 방은 이 계산에서 제외됩니다.)

**예시 JSON:**
1) 부분 예약만 가능한 방만 있는 경우
```json
{
  "min_price_available": null,
  "min_price_partial": 15000
}
```

2) 완전 예약 가능한 방만 있는 경우
```json
{
  "min_price_available": 12000,
  "min_price_partial": null
}
```

3) 두 가지 경우 모두 없거나 예약 불가인 방만 있는 경우
```json
{
  "min_price_available": null,
  "min_price_partial": null
}
```

## 3. 트러블슈팅 이력 (참고)

*   **RoomResult Import Error:** `Union` 타입 문제 해결됨.
*   **PriceRule Alias:** `week` 대신 `days`로 필드명 통일.
*   **권장 인원 계산:** LLM 파싱보다 규칙 기반(`+2 Rule`)을 우선하도록 로직 조정됨.
