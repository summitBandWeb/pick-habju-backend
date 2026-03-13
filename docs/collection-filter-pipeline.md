# 합주실 수집 판별 파이프라인

> 네이버 지도 검색 결과에서 **밴드 합주실만** DB에 저장하기 위한 3단계 필터링 절차.
> 코드 위치: `app/services/room_collection_service.py`

---

## 전체 흐름

```text
네이버 지도 검색
    │
    ▼
[Stage 0] 예약 가능 여부 확인
    │  bookingBusinessId 존재 + business_id 일치
    │
    ▼
[Stage 1] Business 도메인 필터  ──── 합주 키워드 없음 → skipped_non_rehearsal
    │  _evaluate_rehearsal_domain()
    │
    ▼
[Stage 2] Room 레벨 필터  ────────── 전체 룸 탈락 → skipped_all_rooms_filtered
    │  _filter_rooms_for_regex_parsing()
    │
    ▼
[Stage 3] 파싱 + DB 저장
    │  _save_to_db()
    │
    ▼
  DB 저장 완료
```

---

## Stage 0: 예약 가능 여부 확인

**위치**: `collect_priority_areas()` — 검색 결과 순회 시점

| 조건 | 결과 |
|------|------|
| `bookingBusinessId` 없음 | 제외 (네이버 예약 불가) |
| `bookingBusinessId != business_id` | 제외 (ID 불일치) |

이 단계에서 네이버 예약이 불가능한 업체는 수집 대상에서 즉시 제외된다.

---

## Stage 1: Business 도메인 필터

**위치**: `_evaluate_rehearsal_domain()`
**목적**: 해당 업체가 합주실인지 판별

### 합주 키워드 (`REHEARSAL_KEYWORDS`)

```python
"합주실", "합주", "밴드합주"
```

이 3개 키워드만 사용한다. `"음악연습실"`, `"악기연습실"`, `"드럼연습실"` 등은 개인연습실도 매칭되므로 의도적으로 제외했다.

### 키워드 검색 소스 (Waterfall)

아래 순서로 텍스트를 수집하여 합주 키워드 존재 여부를 확인한다:

```text
1순위: Business 이름
       source_hint.name → business.businessDisplayName → business.name

2순위: 소개글 + 예약안내
       source_hint.description, business.desc, business.bookingGuideJson

3순위: 대표 키워드
       representativeKeywords, keywords, tags, hashtagList 등

4순위: 룸 이름 (위 3단계에서 미발견 시만)
       각 room.name에서 키워드 검색
```

### 판정 결과

| 결과 | 동작 |
|------|------|
| 하나 이상 매칭 → `is_candidate=True` | 다음 단계로 진행 |
| 매칭 없음 → `is_candidate=False` | `skipped_non_rehearsal` 반환, 수집 중단 |

### 예시

| 업체 | 매칭 키워드 | 결과 |
|------|-----------|------|
| 그루브 합주실 | `합주실` (이름) | ✅ 통과 |
| 제시뮤직합주실 합정점 | `합주실` (이름) | ✅ 통과 |
| 뮤직 스튜디오 (소개: "밴드합주 가능") | `밴드합주` (소개글) | ✅ 통과 |
| 멜로뮤직 음악연습실 | 없음 | ❌ 탈락 |
| 예쎄뮤직 홍대 피아노 연습실 | 없음 | ❌ 탈락 |
| 아이러브 드럼연습실 | 없음 | ❌ 탈락 |

### source_hint 없는 경우

`collect_by_id()` 직접 호출 시 `source_hint`가 없으면 도메인 필터를 적용하지 않는다. 이는 수동 점검 목적의 호출을 허용하기 위한 의도적 설계이다.

---

## Stage 2: Room 레벨 필터

**위치**: `_filter_rooms_for_regex_parsing()`
**목적**: 개별 룸이 합주실 룸인지 판별

### Sub-filter 2-1: 비합주실 룸 이름 (`_is_non_rehearsal_room_name`)

#### Hard 키워드 (무조건 필터링)

```text
레슨, lesson, 수업, 클래스, 원데이,
기타 대여, 베이스 대여, 앰프 대여, 드럼스틱, 악기 대여,
무용, 댄스, 요가, 필라테스,
파티룸, 촬영, 세미나
```

룸 이름에 위 키워드가 포함되면 무조건 필터링한다.

#### Soft 키워드 (조건부 필터링)

```text
레코딩, recording, 녹음, 믹싱, 마스터링
```

합주실에서 흔히 제공하는 후반작업 서비스이므로, **합주 키워드가 함께 있으면 보존**한다.

| 룸 이름 | 결과 |
|---------|------|
| `합주실 겸 레코딩` | ✅ 보존 (합주실 + 레코딩) |
| `레코딩 스튜디오` | ❌ 필터링 (레코딩만) |

### Sub-filter 2-2: 최소 가격 기준 (`_has_reservation_metadata`)

```python
MIN_REHEARSAL_PRICE = 5000  # 원/시간
```

| 조건 | 결과 |
|------|------|
| `minMaxPrice.minPrice >= 5,000` | ✅ 포함 |
| `room.price >= 5,000` | ✅ 포함 |
| 가격 < 5,000원 또는 없음 | ❌ 제외 |

**근거**: 개인연습실(피아노, 보컬 등)은 보통 시간당 3,000~4,999원대이므로 5,000원을 경계값으로 설정했다. `_has_reservation_metadata` + `_save_to_db` 이중 방어.

### 전체 룸 탈락 시

모든 룸이 필터링되면 해당 업체 전체를 `skipped_all_rooms_filtered`로 처리한다. 사유는 다음 중 하나:

| `reason` | 의미 |
|----------|------|
| `rooms_filtered_non_rehearsal_keywords` | 모든 룸이 비합주실 키워드 |
| `rooms_missing_reservation_metadata` | 모든 룸이 가격 미달 |
| `rooms_filtered_mixed_rules` | 키워드 + 가격 복합 원인 |

---

## Stage 3: DB 저장

**위치**: `_save_to_db()`

Stage 1~2를 통과한 룸만 파싱 후 저장한다. 저장 시 추가 검증:

| 항목 | 규칙 |
|------|------|
| `max_capacity` | 1~50 범위. 0/100은 수동검토 플래그 |
| `recommend_capacity_range` | `[min, max]` — min ≥ 1, max ≤ max_capacity |
| `price_per_hour` | 양수 필수 |
| `name` | parser의 `clean_name` 우선, 없으면 원본 |
| `image_urls` | JSONB 배열. NULL은 빈 배열로 변환 |
| 좌표 | `lat`/`lng` 필수. NULL이면 저장하지 않음 |

상세 필드별 기준은 [db-data-quality-spec.md](./db-data-quality-spec.md) 참조.

---

## 변경 이력

| 날짜 | 변경 내용 |
|------|----------|
| 2026-03-11 | 최초 작성. `REHEARSAL_KEYWORDS` 6개 → 3개 축소, `MIN_REHEARSAL_PRICE` 7,000원 도입 |
| 2026-03-12 | `MIN_REHEARSAL_PRICE` 7,000 → 5,000원 변경. `_save_to_db` 이중 방어 추가. Soft 키워드 Business 레벨 판정 포함 |
