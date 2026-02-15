# 백엔드 추후 구현 필요 사항 (Backend Todo)

본 문서는 `feat/145-metadata-algorithm` 브랜치 작업 이후, 메타데이터 V2의 완전한 정착을 위해 백엔드 팀이 수행해야 할 잔여 작업 및 마이그레이션 가이드입니다.

### 1. 코드 레벨 구현 (Code Implementation)

### 1-1. DTO 입력값 검증 (Issue 1)
- [ ] `AvailabilityRequest` 모델에 Pydantic v2 `field_validator` 적용
    - Date YYYY-MM-DD 정규식 검증
    - Capacity 1~50 범위 제한
    - 422 Unprocessable Entity 에러 매핑 확인

### 1-2. Capacity 100 (Flag) 처리 전략
- [ ] `RoomDetail` DTO (`populate_v2_fields`)
    - DB에 `max_capacity`가 **100**으로 설정된 경우 (수동 검토 필요 플래그), API 응답에서는 `null` 또는 `0`으로 변환하여 클라이언트가 **"문의 필요"** 상태로 인식하게 함.
    - `recommend_capacity_range`가 `[100, 100]`인 경우도 동일하게 처리.

### 1-3. Price Config 구현 (Phased Approach)
- [ ] **Phase 1 (Fallback):** `price_config` 데이터가 없는 경우 (대다수 Legacy), 메모리 상에서 기존 `pricePerHour`를 이용하여 `{"default": pricePerHour}` 설정 생성.
    - `PricingService`는 이미 이 구조를 지원함.
- [ ] **Phase 2 (Crawling):** `RoomParserService` (LLM) 프롬프트 수정
    - 합주실 상세 설명에서 "평일 18시 이후 15000원", "주말 2000원 추가" 등의 텍스트를 파싱하여 JSON 구조로 추출.
- [ ] **Phase 3 (Slot Logic):**
    - 예약 가능 시간(09:00~24:00)을 1시간 단위 슬롯으로 분할하고, Phase 2에서 추출한 Config를 적용하여 시간대별 가격을 계산.

### 1-4. Branch Data Integrity (Issue: Missing Branch Fallback)
- [ ] `RoomCollectionService` 조회 로직 보완
    - 현재 `Inner Join`으로 인해 `branch` 정보가 없는 룸이 조회되지 않는 문제 방어.
    - `Left Join`으로 변경하거나, DTO에서 `branch`가 `None`일 때 Fallback 문자열(예: "지점 정보 없음") 처리 추가.

---

# (부록) Capacity Migration & Compatibility Plan (Original)

기존 `recommendCapacity`(int) 필드와 신규 `recommend_capacity_range`(List[int]) 필드가 공존하는 과도기적 상황에서의 처리 전략 및 구현 계획입니다.

## 1. 현황 분석

*   **AS-IS (Legacy):**
    *   DB/DTO: `recommendCapacity` (int) 필드만 존재.
    *   의미: 대략적인 적정 인원 (최대 인원에 가까운 값).
*   **TO-BE (V2):**
    *   DB: `recommend_capacity_range` (int4range) 컬럼 추가.
    *   DTO: `recommend_capacity_range` (List[int]) 필드 추가 예정.
    *   의미: 최소~최대 권장 인원 (예: `[2, 5]`).

## 2. 호환성 전략 (Coexistence Strategy)

기존 앱/웹 클라이언트와의 호환성을 위해 **두 필드를 모두 내려주는 방식**을 채택합니다.

### Backend (Server)
1.  **DTO 확장:** `RoomDetail` 및 `RoomInfo` 모델에 `recommend_capacity_range: Optional[List[int]]` 필드를 추가합니다.
2.  **Data Population (Up-casting):**
    *   DB에 range 데이터가 **있는** 경우: 그대로 반환.
    *   DB에 range 데이터가 **없는** 경우 (Legacy Data):
        *   기존 `recommendCapacity` 값을 이용하여 임시 범위를 생성합니다.
        *   Rule: `[max(1, recommendCapacity - 2), recommendCapacity]`
        *   *예: 6명 → [4, 6] / 2명 → [1, 2]*

### Frontend (Client)
1.  **UI 우선순위:**
    *   `recommend_capacity_range` 필드가 존재하고 비어있지 않다면 **우선 사용**하여 `Min ~ Max` 형태로 렌더링.
    *   없다면 기존 `recommendCapacity`를 사용하여 `~ N명` 형태로 렌더링.

## 3. 구현 계획 (Action Items)

다음 작업을 `dev` 브랜치(또는 feature 브랜치)에서 수행해야 합니다.

### Step 1: DTO 업데이트
- [ ] `app/models/dto.py`: `RoomDetail` 및 `Response` 모델에 `recommend_capacity_range` 필드 추가.

### Step 2: 변환 로직 구현 (Converter)
- [ ] `app/utils/converters.py` (또는 유사 유틸):
    - `recommendCapacity` -> `List[int]` 변환 헬퍼 함수 구현.
    - DB 조회 시점 또는 API 응답 매핑 시점에, range가 없으면 헬퍼 함수를 통해 기본값을 채워넣는 로직 추가.

### Step 3: 데이터 마이그레이션 (DB)
- [ ] (Optional) 기존 데이터에 대해 일괄적으로 `recommend_capacity_range` 값을 계산하여 DB에 업데이트하는 마이그레이션 스크립트 실행 (조회 시 계산 부하 감소).

## 4. 추가 마이그레이션 (Additional V2 Migration)

Capacity 외에도 V2 호환성을 위해 다음 항목들에 대한 마이그레이션이 필요합니다.

### 4-1. Branch Data Integrity (Missing Branch Fallback)
*   **문제점:** `get_rooms_by_criteria`가 `branch` 테이블과 `Inner Join`을 수행하므로, `branch` 테이블에 지점 정보가 누락된 경우 `room` 데이터가 존재해도 **조회 결과에서 완전히 누락**되는 위험이 있음.
*   **해결 방안:**
    *   `Left Join`으로 쿼리를 변경하거나, `branch` 정보가 없을 때 비상용(Fallback) 지점명을 생성/할당하는 로직 추가.
    *   DTO(`RoomDetail`)에서 `branch` 필드가 `None`으로 넘어올 경우, "지점 정보 없음" 또는 `business_id`를 임시로 표시하도록 처리.

### 4-2. Price Config Defaulting
*   **문제점:** 기존 데이터는 `price_config`(시간/요일별 가격표)가 `NULL`임. V2 가격 계산 로직(`PricingService`)은 `price_config`에 의존함.
*   **해결 방안:**
    *   `price_config`가 없는 경우, 기존 `pricePerHour`를 이용하여 **"전 시간대 단일 가격"** 정책을 동적으로 생성.
    *   Example:
        ```python
        # Default Config Structure (Memory-only)
        {
          "default": pricePerHour,
          "overrides": []
        }
        ```

## 5. 예시 코드 (Draft)

```python
# app/models/dto.py

class RoomDetail(BaseModel):
    # ... 기존 필드 ...
    recommendCapacity: int
    recommend_capacity_range: Optional[List[int]] = Field(None, description="[Min, Max] capacity")
    price_config: Optional[Dict] = Field(None, description="Dynamic price configuration") # New

    @model_validator(mode='after')
    def populate_v2_fields(self):
        """V2 클라이언트를 위한 하위 호환성 보장"""
        # 1. Capacity Range
        if not self.recommend_capacity_range and self.recommendCapacity:
            min_cap = max(1, self.recommendCapacity - 2)
            self.recommend_capacity_range = [min_cap, self.recommendCapacity]
            
        # 2. Price Config (Simple Conversion)
        if not self.price_config and self.pricePerHour:
             self.price_config = {"default": self.pricePerHour}
             
        return self
```
## 6. DB Migration Guide (For DBA/Peer Review)

DB 스키마 변경을 담당하는 팀원을 위한 가이드입니다. 다음 SQL을 실행하여 `room` 테이블을 V2 스펙으로 업그레이드해주세요.

### 6-1. Schema Update SQL

```sql
-- 1. Capacity V2 Fields
ALTER TABLE room 
ADD COLUMN IF NOT EXISTS recommend_capacity_range int4range,
ADD COLUMN IF NOT EXISTS base_capacity integer DEFAULT NULL,
ADD COLUMN IF NOT EXISTS extra_charge integer DEFAULT NULL;

-- 2. Dynamic Pricing Config
ALTER TABLE room
ADD COLUMN IF NOT EXISTS price_config jsonb DEFAULT NULL;

-- 3. Comments (Optional documentation)
COMMENT ON COLUMN room.recommend_capacity_range IS '권장 인원 범위 [min, max]';
COMMENT ON COLUMN room.base_capacity IS '추가 요금 발생 기준 인원';
COMMENT ON COLUMN room.extra_charge IS '1인당 시간당 추가 요금';
COMMENT ON COLUMN room.price_config IS '요일/시간대별 동적 가격 설정 (JSON)';
```

### 6-2. Data Backfilling Strategy (권장)

기존 데이터에 대해 `NULL` 값을 방지하고 조회 성능을 높이기 위해, 다음 마이그레이션 쿼리 실행을 권장합니다.

```sql
-- Legacy recommend_capacity(int) 값을 이용하여 range 초기화
-- 범위 규칙: [max(1, N-2), N]
UPDATE room
SET recommend_capacity_range = int4range(
  GREATEST(1, recommend_capacity - 2), 
  recommend_capacity, 
  '[]' -- inclusive bounds
)
WHERE recommend_capacity IS NOT NULL 
  AND recommend_capacity_range IS NULL;

-- Legacy price_per_hour 값을 이용하여 price_config 기본 구조 생성
UPDATE room
SET price_config = jsonb_build_object(
  'default', price_per_hour,
  'overrides', '[]'::jsonb
)
WHERE price_per_hour IS NOT NULL 
  AND price_config IS NULL;
```
