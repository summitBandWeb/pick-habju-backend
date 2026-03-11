# DB 데이터 품질 기준서

> DB에 저장된 값이 그대로 프론트엔드로 전달되므로, **저장 시점에서 사용자에게 보여줄 수 있는 상태**여야 한다.

---

## 1. Branch (지점)

| 필드 | 기준 | 나쁜 예 | 좋은 예 |
|------|------|---------|---------|
| `name` / `display_name` | 지점명만. 룸명, 예약 안내 문구 포함 금지 | `월-목 / 금토일 예약`, `방문 상담` | `비쥬 합주실 1호점` |
| `lat` / `lng` | 필수. NULL이면 저장하지 않음. 위경도 뒤바뀜 자동 보정 | `lat=126.9, lng=37.5` | `lat=37.5, lng=126.9` |
| `phone_number` | 한국 전화번호 형식만. 0507 안심번호 포함. NULL 허용 | `없음`, `문의` | `010-1234-5678`, `0507-1234-5678`, `02-123-4567`, `NULL` |
| `standby_days` | 예약 오픈까지 남은 일수. NULL 허용 | — | `7`, `14`, `NULL` |
| 서비스 지역 | `is_in_service_area()` 통과하는 좌표만 저장 | 강남, 송파 등 서비스 외 | 역 기준 2km 이내 |

---

## 2. Room 이름 (`name`)

### 원칙: 사용자가 **어떤 방인지** 즉시 알 수 있어야 한다.

| 규칙 | 설명 | 제거 대상 예시 |
|------|------|-------------|
| 프로모션/이벤트 태그 제거 | `[개강특가]`, `[EVENT]`, `[할인]` 등 시한성 문구 | `[개강특가] 블랙룸` -> `블랙룸` |
| 시간대/요일 운영 태그 제거 | `[평일]`, `(주말)`, `심야 한정` 등. **단, 시간대별 요금 구분 룸은 태그 유지** (아래 예외 참조) | `[블랙룸 심야 한정 운영] 블랙룸` -> `블랙룸` |
| 가격 정보 제거 | 이름에 포함된 요금 표기 | `A룸 15000원/시간` -> `A룸` |
| 인원 정보는 **파싱 후 제거** | 이름의 인원 정보는 `max_capacity`, `recommend_capacity_range`로 추출 후 이름에서 제거 | `블랙룸 (정원 20명, 최대 30명)` -> `블랙룸` |
| 룸 식별자만 남김 | 최종 이름은 방 이름 or 알파벳/번호 | `Room R`, `A룸`, `화이트룸`, `1번방` |

### 예외: 시간대별 요금 구분 룸

네이버 예약에서 같은 물리 룸이 시간대별 다른 요금으로 등록된 경우 (예: `블랙룸 (평일 낮)`, `블랙룸 (심야)`), 각각 별도 `biz_item_id`를 가지므로 **시간대 태그를 유지한다**. 태그를 제거하면 같은 이름의 룸이 중복 표시되어 사용자 혼란을 유발한다.

### 비합주실 룸 필터링

아래 키워드가 포함된 룸은 **저장하지 않는다**:

```text
기타 대여, 베이스 대여, 앰프 대여, 드럼스틱, 악기 대여,
레슨, 수업, 클래스, 원데이,
녹음, 레코딩, 믹싱, 마스터링,
무용, 댄스, 요가, 필라테스,
파티룸, 촬영, 세미나
```

---

## 3. 인원수

### 원칙: 사용자가 **몇 명이서 갈 수 있는지** 신뢰할 수 있어야 한다.

| 필드 | 의미 | 기준 |
|------|------|------|
| `max_capacity` | 이 방에 들어갈 수 있는 최대 인원 | 1~50 범위. 0이나 100(수동검토)은 프론트에서 "인원 미확인"으로 표시 |
| `recommend_capacity_range` | 쾌적하게 합주할 수 있는 인원 범위 `[min, max]` | min >= 1, max <= max_capacity, min <= max |
| `base_capacity` | 추가 요금 없이 이용 가능한 인원 | base <= max_capacity |
| `extra_charge` | base 초과 시 1인당 추가 요금(원) | 양수 정수. 추가 요금이 없으면 NULL |

### 논리 규칙

```text
1 <= recommend_range[0] <= recommend_range[1] <= max_capacity <= 50
base_capacity <= max_capacity (base가 있을 때)
```

### 값 결정 우선순위

```text
1순위: 네이버 룸 설명의 명시적 텍스트 ("정원 3명, 최대 4명")
2순위: 파서의 정규식 추출 결과
3순위: 기존 DB 유효값 보존 (새 값이 기본값일 때)
최종:  수동검토 플래그(100) -> 프론트에서 "인원 미확인" 표시
```

### 금지 사항
- `recommend_range = [20, 20]`처럼 같은 값 쌍은 단일값으로 처리 -> `[20, 20]` 허용하되, 프론트에서 "20명" 표시
- `max_capacity = 100`은 수동검토 플래그이므로 절대 프론트에 그대로 노출하지 않음 (DTO에서 0으로 변환됨)

---

## 4. 가격

### 원칙: 사용자가 **얼마인지** 바로 알 수 있어야 한다.

| 필드 | 의미 | 기준 |
|------|------|------|
| `price_per_hour` | 시간당 기본 요금 (원) | 양수 필수. 0원이면 저장하지 않음 |
| `price_config` | 시간대/요일별 동적 가격 | `{"default": 15000, "overrides": [...], "surcharges": [...]}` |

### 규칙
- **시간당 7,000원 미만 룸은 수집하지 않는다** (`MIN_REHEARSAL_PRICE = 7000`, `_has_reservation_metadata`에서 제외)
- 개인연습실(피아노, 보컬 등)은 보통 3,000~6,000원대이므로 7,000원 기준으로 자연 탈락
- `price_config`가 NULL이면 `price_per_hour`를 default로 자동 생성

---

## 5. 정책 플래그

| 필드 | 의미 | 프론트 표시 |
|------|------|-----------|
| `can_reserve_one_hour` | 1시간 단위 예약 가능 여부 | false면 "최소 2시간" 경고 |
| `requires_call_on_sameday` | 당일 예약 시 전화 필요 | true면 "당일 예약은 전화 문의" 경고 |

---

## 6. 이미지 (`image_urls`)

- `room` 테이블의 `image_urls` JSONB 컬럼에 배열로 저장
- 빈 배열 `[]` 허용, NULL은 DTO에서 빈 배열로 변환
- URL은 `https://` 로 시작하는 유효한 이미지 URL만
- 배열 순서가 프론트 노출 순서

---

## 7. 수집 제외 대상 (DB에 저장하지 않는 것)

| 조건 | 이유 |
|------|------|
| 서비스 지역(역 2km) 외 | 서비스 범위 밖 |
| `bookingBusinessId` 없음 | 네이버 예약 불가 |
| 합주 키워드 미매칭 (`합주실`, `합주`, `밴드합주`) | 합주실이 아님 |
| 가격 7,000원 미만 또는 없음 | 개인연습실이거나 유효한 예약 정보 제공 불가 |
| 악기 대여/레슨/녹음 등 비합주실 룸 | 합주실 룸이 아님 |
| 좌표 NULL | 지도에 표시 불가 |

---

## 8. 수집 판별 파이프라인

상세 판별 절차는 [collection-filter-pipeline.md](./collection-filter-pipeline.md) 참조.

---

## 9. 데이터 정합성 체크리스트

배포 전 아래 쿼리로 검증:

```sql
-- 1) 수동검토 플래그가 남아있는 룸
SELECT count(*) FROM room WHERE max_capacity = 100;

-- 2) 가격 7,000원 미만 룸 (개인연습실 혼입 여부)
SELECT count(*) FROM room WHERE price_per_hour < 7000;

-- 3) 이름에 프로모션 태그가 남아있는 룸
SELECT count(*) FROM room WHERE name ~ '\[.*(특가|할인|이벤트|EVENT).*\]';

-- 4) 좌표 NULL인 branch
SELECT count(*) FROM branch WHERE lat IS NULL OR lng IS NULL;

-- 5) 인원수 논리 위반 (recommend_capacity_range 기준)
SELECT count(*) FROM room
WHERE upper(recommend_capacity_range) > max_capacity
   OR max_capacity > 50
   OR max_capacity <= 0;

-- 6) price_config 백필 누락 (price_per_hour가 있는데 price_config가 NULL)
SELECT count(*) FROM room
WHERE price_per_hour > 0 AND price_config IS NULL;

-- 7) 비룸 데이터 혼입 (안내성 문구)
SELECT count(*) FROM room
WHERE name ~* '당일.*예약|전화.*문의|이벤트.*예약|견적|공지|안내';

-- 8) 위경도 뒤바뀜 (lat > 100)
SELECT count(*) FROM branch WHERE lat > 100;

-- 9) price_per_hour = 0 (무료 룸)
SELECT count(*) FROM room WHERE price_per_hour = 0;
```
