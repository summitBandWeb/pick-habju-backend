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

**인식하는 시간대 키워드** (`_TIME_SLOT_KEYWORDS`):

```text
평일 낮, 평일낮, 평일 오전, 평일 야간, 평일, 주말, 공휴일, 주말/공휴일, 심야, 야간, 주간
```

### 이름 정제 파이프라인 (`_clean_room_name`)

| 단계 | 대상 | 예시 |
|------|------|------|
| 1. Leading bracket 프로모션 제거 | `[특가]`, `[할인]`, `[이벤트]`, `[평일]`, `[운영]`, `[예약]` 등 | `[개강특가] 블랙룸` → `블랙룸` |
| 2. 시간대 태그 감지 & 보존 | bracket 안에 시간대 키워드 있으면 레이블로 이동 | `[평일 야간] 2번방` → `2번방 (평일 야간)` |
| 3. 이벤트 프리픽스 제거 | `EVENT))`, `이벤트)` 등 | `EVENT))1번방` → `1번방` |
| 4. 인원 정보 파싱 후 제거 | `(정원 N명, 최대 M명)`, `(- N명)` | `블랙룸 (정원 20명)` → `블랙룸` |
| 5. Trailing 운영안내 괄호 제거 | `(예약 필수)`, `(전화 문의)`, `(할인 10%)` 등 | `A룸 (당일 전화문의)` → `A룸` |

### 비합주실 룸 필터링

#### Hard 키워드 — 무조건 제외 (`NON_REHEARSAL_ROOM_NAME_KEYWORDS`)

```text
# 교육/레슨
레슨, lesson, 수업, 클래스, 원데이

# 악기 대여
기타 대여, 베이스 대여, 앰프 대여, 드럼스틱, 악기 대여, 피아노 대여, 피아노스튜디오

# 비음악 용도
무용, 댄스, 요가, 필라테스

# 결제/상품
쿠폰, 선불권, 이용권, 월대여

# 기타
파티룸, 촬영, 세미나
```

#### Soft 키워드 — 조건부 보존 (`NON_REHEARSAL_SOFT_KEYWORDS`)

```text
레코딩, recording, 녹음, 믹싱, 마스터링
```

**로직**: 해당 business가 합주실로 판별된 경우 → 보존. 아닌 경우 → 룸 이름에 합주 키워드(`합주실`, `합주` 등)가 있으면 보존, 없으면 제외.

---

## 3. 인원수

### 원칙: 사용자가 **몇 명이서 갈 수 있는지** 신뢰할 수 있어야 한다.

### 필드 정의

| 필드 | 의미 | 기준 |
|------|------|------|
| `max_capacity` | 이 방에 들어갈 수 있는 최대 인원 | 1~50 범위. 0이나 100(`MANUAL_REVIEW_FLAG`)은 프론트에서 "인원 미확인" 표시 |
| `recommend_capacity_range` | 쾌적하게 합주할 수 있는 인원 범위 `[min, max]` | min >= 1, max <= max_capacity, min <= max |
| `recommend_capacity` | (legacy) 단일 추천 인원값 | DTO에서 제거됨. DB 컬럼은 의존성 때문에 유지. 향후 완전 제거 예정 |
| `base_capacity` | 추가 요금 없이 이용 가능한 인원 | base <= max_capacity |
| `extra_charge` | base 초과 시 1인당 추가 요금(원) | 양수 정수. 추가 요금이 없으면 NULL |

### 논리 규칙

```text
1 <= recommend_range[0] <= recommend_range[1] <= max_capacity <= 50
base_capacity <= max_capacity (base가 있을 때)
MANUAL_REVIEW_FLAG(100) 이상이면 현실적 상한 50으로 clamp
```

### `max_capacity` 결정 우선순위

```text
1순위: 텍스트 신호 — 룸 설명의 명시적 텍스트 ("정원 3명, 최대 4명", "4~6명")
2순위: 파서 출력 — 정규식 추출 결과
3순위: 가격 기반 추론 — business별 룰 매칭 → 가격대별 기본값
4순위: 기존 DB 유효값 보존 (새 값이 기본값 0/1일 때)
최종:  MANUAL_REVIEW_FLAG(100) → 프론트에서 "인원 미확인" 표시
```

### `recommend_capacity_range` 계산 (`_calculate_capacity_range`)

```text
1. parsed_range 유효 (2개 값, min<=max, 1~50 범위)
   → [clamped_min, min(clamped_max, max_capacity)] 반환

2. MANUAL_REVIEW_FLAG 방어
   → max_cap/rec_cap/base_cap 중 100 이상이면 50으로 clamp

3. extra_charge 있는 경우 (추가 요금 체계)
   → [base_capacity, max(max_capacity, base_capacity)]

4. extra_charge 없는 경우 (기본)
   delta = 2 (rec_cap >= 9) / 1 (rec_cap < 9)
   → [max(rec_cap - delta, 1), min(rec_cap + delta, max_capacity)]
```

### 가격 기반 인원수 추론

파서/텍스트에서 인원수를 얻지 못했을 때 가격대로 추론한다.

**Step 1: Business별 맞춤 룰** (`PRICE_CAPACITY_RULES`) — 특정 업체 가격-인원 매핑이 등록된 경우 우선 적용. 가격 차이 `PRICE_MATCH_TOLERANCE(1000원)` 이내면 매칭.

**Step 2: 가격대별 기본값** (`PRICE_BAND_CAPACITY_DEFAULTS`)

| 가격대 | max_capacity | recommend_range |
|--------|-------------|----------------|
| 10,000~14,999원 | 8 | [3, 5] |
| 15,000~19,999원 | 11 | [6, 8] |
| 20,000원 이상 | 15 | [8, 12] |

### 키워드 기반 인원수 (`KEYWORD_CAPACITY_MAP`)

룸 이름에 아래 키워드가 있으면 max_capacity 힌트로 사용:

| 키워드 | max_capacity |
|--------|-------------|
| `대형`, `대합주실` | 15 |
| `중형` | 8 |
| `소형`, `소합주실` | 4 |

### `base_capacity` / `extra_charge` 추출

```text
1순위: Structured JSON — extraFeeSettingJson 파싱
       key hints: extrafee, extra_fee, additionalfee, surcharge, amount
2순위: Regex — "기본 N명", "1인 추가 N원", "인당 추가 N원"
```

### 금지 사항
- `recommend_range = [20, 20]`처럼 같은 값 쌍 → 허용하되, 프론트에서 "20명" 표시
- `max_capacity = 100`은 수동검토 플래그이므로 절대 프론트에 그대로 노출하지 않음 (DTO에서 0으로 변환)

---

## 4. 가격

### 원칙: 사용자가 **얼마인지** 바로 알 수 있어야 한다.

| 필드 | 의미 | 기준 |
|------|------|------|
| `price_per_hour` | 시간당 기본 요금 (원) | 양수 필수. 0원이면 저장하지 않음 |
| `price_config` | 시간대/요일별 동적 가격 | `{"default": 15000, "overrides": [...], "surcharges": [...]}` |

### 규칙
- **시간당 5,000원 미만 룸은 수집하지 않는다** (`MIN_REHEARSAL_PRICE = 5000`, `_has_reservation_metadata` + `_save_to_db` 이중 방어)
- 개인연습실(피아노, 보컬 등)은 보통 3,000~4,999원대이므로 5,000원 기준으로 자연 탈락
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

## 7. 수집 대상 판별

### 합주 키워드 (`REHEARSAL_KEYWORDS`)

```text
합주실, 합주, 밴드합주, 악기연습실, 드럼연습실
```

**키워드 검색 소스** (waterfall — 위에서 발견되면 아래 생략):
1. 대표 키워드 필드 (`representativeKeywords`, `keywords`, `tags`, `hashtagList`, `hashtag`)
2. Business 이름 + 소개(description) + 예약안내(bookingGuideJson)
3. 룸 이름 (위 2단계에서 미발견 시)

### 대표 키워드 추출 — 3중 방어 구조

검색 페이지 Apollo State에는 키워드 필드가 없으므로, **place 상세 페이지 Playwright 방문**이 유일한 경로.

| 계층 | 방법 | 설명 |
|------|------|------|
| 1차 | Apollo State walk | 상세 페이지 iframe의 `__APOLLO_STATE__`에서 `keyword/hashtag/tag` 키 탐색 (depth 6, 최대 40개) |
| 2차 | DOM 텍스트 fallback | body inner_text에서 "대표 키워드" 마커 이후 섹션 파싱 (토큰 60자 이하, section break: `startswith("편의", "SNS", ...)`) |
| 3차 | 재시도 | 1차+2차 모두 빈 결과 시, 추가 대기(`INFO_TAB_RENDER_WAIT_MS` + jitter) 후 1회 재시도 |

최종: Apollo + DOM 병합 → 중복 제거 → 최대 20개 정규화.

### 네거티브 필터

| 필터 | 상수 | 내용 |
|------|------|------|
| Business 이름 네거티브 | `NON_REHEARSAL_BUSINESS_NAME_KEYWORDS` | `"피아노"` — 이름에 있고 `"합주"/"밴드"`가 없으면 제외 |
| 차단 목록 | `BLACKLISTED_BUSINESS_IDS` | `570236` (타수 음악연습실), `1708894171` (타수 2호점) — 합주실 사칭 |

### 수집 제외 조건 (DB에 저장하지 않는 것)

| 조건 | 이유 |
|------|------|
| 서비스 지역(역 2km) 외 | 서비스 범위 밖 |
| `bookingBusinessId` 없음 | 네이버 예약 불가 |
| 합주 키워드 5개 모두 미매칭 | 합주실이 아님 |
| Business 이름 네거티브 필터 해당 | 피아노 교실 등 비합주 업종 |
| `BLACKLISTED_BUSINESS_IDS` 해당 | 수동 차단된 사업체 |
| 가격 5,000원 미만 또는 없음 | 개인연습실이거나 유효한 예약 정보 제공 불가 |
| 비합주실 룸 (hard 키워드 17개) | 합주실 룸이 아님 (Section 2 참조) |
| 좌표 NULL | 지도에 표시 불가 |

---

## 8. 수집 판별 파이프라인

상세 판별 절차는 [collection-filter-pipeline.md](./collection-filter-pipeline.md) 참조.

```text
네이버 지도 검색 (PRIORITY_AREA_QUERIES: "이수역 합주실" 등 8개 쿼리)
    ↓
[Stage 0] 예약 가능 여부 — bookingBusinessId 존재 + 일치
    ↓
[Stage 1] Business 도메인 필터 — 합주 키워드 5개 + 네거티브 필터 + 블랙리스트
    ↓
[Stage 2] Room 레벨 필터 — Hard 17개 + Soft 5개(조건부) + 최소 가격 5,000원
    ↓
[Stage 3] 파싱 + DB 저장 — 이름 정제, 인원수 추출, 가격 설정
```

---

## 9. 데이터 정합성 체크리스트

배포 전 아래 쿼리로 검증:

```sql
-- 1) 수동검토 플래그가 남아있는 룸
SELECT count(*) FROM room WHERE max_capacity = 100;

-- 2) 가격 5,000원 미만 룸 (개인연습실 혼입 여부)
SELECT count(*) FROM room WHERE price_per_hour < 5000;

-- 3) 이름에 프로모션 태그가 남아있는 룸
SELECT count(*) FROM room WHERE name ~ '\[.*(특가|할인|이벤트|EVENT).*\]';

-- 4) 좌표 NULL인 branch
SELECT count(*) FROM branch WHERE lat IS NULL OR lng IS NULL;

-- 5) 인원수 논리 위반 (recommend_capacity_range 기준)
-- recommend_capacity_range는 integer[] 타입 (1-indexed: [1]=하한, [2]=상한)
SELECT count(*) FROM room
WHERE (recommend_capacity_range IS NOT NULL AND recommend_capacity_range[2] > max_capacity)
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

-- 10) 차단 목록 business가 DB에 남아있는지
SELECT count(*) FROM branch WHERE naver_business_id IN ('570236', '1708894171');

-- 11) 비합주실 룸 이름 키워드 혼입 (hard keywords)
SELECT count(*) FROM room
WHERE name ~* '레슨|lesson|수업|클래스|원데이|기타 대여|베이스 대여|피아노 대여|피아노스튜디오|무용|댄스|요가|필라테스|쿠폰|선불권|이용권|월대여|파티룸|촬영|세미나';

-- 12) recommend_capacity_range 하한이 상한보다 큰 경우
SELECT count(*) FROM room
WHERE recommend_capacity_range IS NOT NULL
  AND recommend_capacity_range[1] > recommend_capacity_range[2];
```
