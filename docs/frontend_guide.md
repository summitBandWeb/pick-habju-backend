# 프론트엔드 연동 가이드 (Metadata V2)

본 문서는 합주실 예약 시스템의 메타데이터 품질 향상 버전(v2.0)에 맞춰 프론트엔드에서 연동해야 할 API 응답 구조 및 UI 처리 가이드입니다.

## 1. 구현 가이드 (Frontend Action Items)

백엔드 배포 단계에 따라 프론트엔드 대응 전략이 나뉩니다.

### 1-1. 현재 브랜치 머지 직후 (v2.0.0-alpha)
**즉시 적용 가능한 UI 변경 사항입니다.**

1.  **인원 표기 (Capacity Range):**
    *   `recommend_capacity_range` 배열(`[min, max]`)이 존재하면 **"2~6명"** 형태로 우선 표기해 주세요.
    *   없으면 기존대로 `~4명` 또는 `최대 6명` 표기 (Legacy 호환).
2.  **정책 경고 (Policy Warnings):**
    *   `policy_warnings` 배열에 문자열이 있으면, 예약 시도 시 또는 룸 선택 시 **Toast/Tooltip**으로 사용자에게 반드시 안내해야 합니다.
    *   *예: "당일 예약은 전화 문의가 필요합니다."*

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

### Phase 4: API 응답 정규화 (Response Structure)

API 응답(`AvailabilityResponse`)의 전체 구조는 다음과 같습니다. 기존 필드를 유지하면서 `results` 내부의 `room_detail`이 v2 구조로 확장되고, 최상위에 `branch_summary`가 추가되었습니다.

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
  "results": [
    {
      "room_detail": {
        "name": "A룸",
        "branch": "그라운드합주실 신촌1호점",
        "business_id": "1182602",
        "biz_item_id": "5979448",
        "imageUrls": [
          "https://example.com/image1.jpg"
        ],
        "maxCapacity": 6,
        "recommendCapacity": 4,          // [Legacy] 하위 호환성 유지
        "recommend_capacity_range": [2, 6], // [NEW] 권장 인원 범위
        "base_capacity": 4,              // [NEW]
        "extra_charge": 5000,            // [NEW]
        "pricePerHour": 15000,           // 기준 가격
        "canReserveOneHour": true,
        "requiresCallOnSameDay": false,
        "estimated_price": 45000,        // [NEW] 계산된 최종 예상 가격
        "policy_warnings": [             // [NEW] 정책 위반 시 경고
          "당일 예약은 전화 문의가 필요합니다."
        ]
      },
      "available": "unknown",     // [UPDATE] true / false / "unknown" 가능
      "available_slots": {
        "17:00": true,
        "18:00": false
      }
    }
  ],
  "branch_summary": {                    // [NEW] 지도 마커용 지점 요약
    "그라운드합주실 신촌1호점": {
      "min_price": 12000,
      "available_count": 2,
      "lat": 37.556,
      "lng": 126.937
    }
  }
}
```
### 4-1. `available` 필드 상태값 (Enum)
*   `true` (Boolean): 예약 가능
*   `false` (Boolean): 예약 불가 (이미 예약됨)
*   `"unknown"` (String): **상태 알 수 없음** (오픈 대기 기간 등)
    *   UI 처리: 회색 처리 또는 "오픈 예정" 뱃지 표시 권장

## 3. 트러블슈팅 이력 (참고)

*   **RoomResult Import Error:** `Union` 타입 문제 해결됨.
*   **PriceRule Alias:** `week` 대신 `days`로 필드명 통일.
*   **권장 인원 계산:** LLM 파싱보다 규칙 기반(`+2 Rule`)을 우선하도록 로직 조정됨.
