# 네이버 합주실 데이터 수집 시스템

> **목적**: 네이버 지도와 예약 시스템에 흩어진 합주실 정보를 자동으로 수집하여 통합 DB에 저장합니다.

---

## 1. 왜 이 시스템이 필요한가?

### 1.1 문제 상황

밴드 연습실을 찾는 사용자는 다음과 같은 불편을 겪습니다:

| 단계 | 현재 방식 | 문제점 |
|:----:|----------|--------|
| 🔍 탐색 | 네이버 지도에서 "합주실" 검색 | 지역별로 반복 검색 필요 |
| 📋 정보 확인 | 각 합주실 상세 페이지 방문 | 룸 정보가 일관되지 않음 |
| 📞 예약 확인 | 네이버 예약 또는 전화 문의 | 실시간 확인 불가 |
| 🤔 결정 | 가격/위치/시간 종합 판단 | 정보가 흩어져 있음 |

### 1.2 해결 방안

```
[ 분산된 합주실 정보 ]  ───▶  [ Pick 합주 통합 DB ]  ───▶  [ 사용자: 한 곳에서 비교/예약 ]
     (네이버 지도)                 (Supabase)                    (Mobile App)
```

**핵심 가치**:
- 🗺️ **One-Stop Search**: 여러 플랫폼을 오갈 필요 없이 한 앱에서 모든 정보 확인
- 📊 **Data Consistency**: LLM 파싱 + 수동 보정으로 데이터 정확도 유지
- 🇰🇷 **Nationwide Coverage**: 서울뿐 아니라 전국 주요 도시 합주실 정보 제공

---

## 2. 시스템 아키텍처

### 2.1 전체 데이터 파이프라인

```
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                              Room Collection Pipeline                               │
├─────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                     │
│   ① DISCOVER              ② FETCH                ③ PARSE              ④ SAVE      │
│  ┌──────────────┐       ┌──────────────┐       ┌──────────────┐    ┌────────────┐  │
│  │ NaverMap     │ ───▶  │ RoomFetcher  │ ───▶  │ RoomParser   │ ──▶│ Supabase   │  │
│  │ Crawler      │       │ (GraphQL)    │       │ (LLM+Regex)  │    │ DB         │  │
│  │              │       │              │       │              │    │            │  │
│  │ • Playwright │       │ • bizItems   │       │ • Gemini API │    │ • branch   │  │
│  │ • 전국 검색   │       │ • business   │       │ • Fallback   │    │ • room     │  │
│  └──────────────┘       └──────────────┘       └──────────────┘    └────────────┘  │
│        ▲                                                                  │        │
│        │                    Data Preservation                             │        │
│        │                  ┌─────────────────────┐                        │        │
│        └──────────────────│ 기존 값과 비교 후    │◀───────────────────────┘        │
│                           │ 유효한 값 유지       │                                  │
│                           └─────────────────────┘                                  │
│                                                                                     │
└─────────────────────────────────────────────────────────────────────────────────────┘
```

### 2.2 주요 컴포넌트 설명

| 컴포넌트 | 파일 | 역할 | 기술 스택 |
|----------|------|------|-----------|
| **Orchestrator** | `room_collection_service.py` | 전체 수집 프로세스 조율 | Python, asyncio |
| **Discoverer** | `naver_map_crawler.py` | 네이버 지도에서 합주실 ID 수집 | Playwright |
| **Fetcher** | `naver_room_fetcher.py` | GraphQL API로 상세 정보 수집 | httpx |
| **Parser** | `room_parser_service.py` | 비정형 텍스트 → 정형 데이터 | Gemini LLM |
| **CLI** | `collect_rooms.py` | 터미널 실행 인터페이스 | argparse |

---

## 3. 핵심 기능 상세

### 3.1 전국 단위 병렬 수집 (Nationwide Crawling)

#### 왜 병렬 수집인가?
- 순차 수집 시 **35개 지역 × 평균 5초 = 약 3분** 소요
- 병렬 수집 시 **동시 3개 × 12회 = 약 1분** 으로 단축
- `asyncio.Semaphore`로 브라우저 과부하 방지

#### 대상 지역
```python
# 서울 25개 구
seoul_districts = ["강남구", "마포구", "송파구", ...]  # 25개

# 광역시 및 주요 도시
major_cities = ["부산", "대구", "인천", "광주", "대전", "울산", 
                "수원", "성남", "고양", "부천"]
```

#### 실행 방법
```bash
# 전국 자동 수집
python scripts/collect_rooms.py --auto

# 특정 지역만 수집 (테스트용)
python scripts/collect_rooms.py --query "홍대 합주실"

# 특정 합주실 업데이트
python scripts/collect_rooms.py --id "522011"
```

---

### 3.2 데이터 보존 로직 (Data Preservation)

#### 왜 필요한가?
LLM 파싱이 때때로 실패하거나 보수적으로 `max_capacity=1`을 반환합니다.
수동으로 정확한 값(예: `10`)을 입력해두었는데, 다음 크롤링 시 `1`로 덮어씌워지면 곤란합니다.

#### 동작 원리
```
┌─────────────────────────────────────────────────────────────────┐
│                    Data Preservation Logic                      │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│   새로운 파싱 값         기존 DB 값           최종 저장 값        │
│   ─────────────         ──────────           ────────────        │
│                                                                 │
│   max_capacity = 1  +   max_capacity = 10  →  max_capacity = 10 │
│   (파싱 실패/기본값)     (수동 입력)            (기존 값 유지)     │
│                                                                 │
│   max_capacity = 5  +   max_capacity = 10  →  max_capacity = 5  │
│   (유효한 파싱 결과)     (이전 값)              (새 값으로 갱신)   │
│                                                                 │
│   max_capacity = 8  +   max_capacity = 1   →  max_capacity = 8  │
│   (유효한 파싱 결과)     (기본값)               (새 값으로 갱신)   │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

**핵심 규칙**: 
> 새 값이 기본값(0 또는 1)이고, 기존 값이 유효(>1)하면 → **기존 값 유지**

---

### 3.3 LLM 파싱 (Room Parser)

#### 파싱 대상 필드

| 필드 | 입력 예시 | 출력 |
|------|----------|------|
| `max_capacity` | `"최대 10명 수용 가능"` | `10` |
| `recommend_capacity` | `"4~6인 권장"` | `5` |
| `extra_charge` | `"인당 3,000원 추가"` | `3000` |
| `requires_call_on_same_day` | `"당일 예약은 전화 문의"` | `true` |

#### 장애 대응
```
Gemini API 호출
      │
      ├── 성공 → JSON 파싱 → 결과 반환
      │
      └── 실패 (할당량 초과, 네트워크 오류)
              │
              └── Regex Fallback → 패턴 매칭으로 추출
```

---

## 4. 데이터베이스 스키마

### 4.1 테이블 구조

```sql
-- 지점 정보
CREATE TABLE branch (
    business_id VARCHAR(50) PRIMARY KEY,  -- 네이버 Business ID
    name        VARCHAR(100) NOT NULL      -- 지점명 (예: 비쥬합주실 1호점)
);

-- 룸 정보
CREATE TABLE room (
    business_id         VARCHAR(50) NOT NULL,  -- FK → branch
    biz_item_id         VARCHAR(50) NOT NULL,  -- 룸 고유 ID
    name                VARCHAR(100) NOT NULL, -- 룸명 (예: 블랙룸)
    
    max_capacity        INTEGER DEFAULT 1,     -- 최대 인원
    recommend_capacity  INTEGER DEFAULT 1,     -- 권장 인원
    price_per_hour      NUMERIC(15,2),         -- 시간당 가격
    
    image_urls          JSONB,                 -- 이미지 URL 배열
    requires_call_on_sameday BOOLEAN DEFAULT FALSE,
    
    PRIMARY KEY (business_id, biz_item_id)
);
```

### 4.2 이미지 저장 방식

> **설계 결정**: 별도 `room_image` 테이블 대신 `image_urls` JSONB 컬럼 사용

**이유**:
- 이미지는 단순 URL 목록이므로 별도 테이블 불필요
- JOIN 없이 빠른 조회 가능
- 스키마 변경 없이 유연하게 데이터 추가 가능

```json
// room.image_urls 예시
["https://example.com/room1.jpg", "https://example.com/room2.jpg"]
```

---

## 5. 파일 구조

```
app/
├── core/
│   └── database.py              # Supabase 클라이언트 초기화
│
├── crawler/
│   ├── naver_map_crawler.py     # ① 네이버 지도 검색 (Playwright)
│   └── naver_room_fetcher.py    # ② GraphQL 상세 정보 수집
│
├── services/
│   ├── room_parser_service.py   # ③ LLM + Regex 파싱
│   └── room_collection_service.py  # Orchestrator (전체 조율)
│
├── models/
│   └── dto.py                   # RoomDetail 등 데이터 모델
│
└── utils/
    └── room_loader.py           # DB 조회 유틸리티

scripts/
└── collect_rooms.py             # CLI 진입점 (--query, --id, --auto)

migrations/
└── 001_create_room_tables.sql   # 스키마 참고용
```

---

## 6. 진행 상황

| Phase | 항목 | 상태 | 비고 |
|:-----:|------|:----:|------|
| **1** | GraphQL Fetcher | ✅ | `naver_room_fetcher.py` |
| | LLM Parser | ✅ | Gemini + Regex Fallback |
| **2** | Supabase 연동 | ✅ | JSONB 이미지 저장 방식 |
| | CLI 스크립트 | ✅ | `--query`, `--id`, `--auto` 지원 |
| **3** | 전국 수집 확장 | ✅ | 35개 지역 병렬 크롤링 |
| | 데이터 보존 로직 | ✅ | 수동 입력 데이터 보호 |
| **4** | 운영 자동화 | ⏳ | GitHub Actions / Cron 예정 |
| | Discord 알림 | ⏳ | 검수용 Webhook 예정 |

---

## 7. 트러블슈팅 기록

### 해결된 이슈

| 이슈 | 원인 | 해결 방법 |
|------|------|----------|
| GraphQL 필드 오류 | `roadAddress`, `phone` 필드 미존재 | 쿼리에서 해당 필드 제거 |
| Gemini 모델 404 | `1.5-flash` 지원 중단 | `2.0-flash`로 변경 |
| `PGRST204` 에러 | `created_at` 컬럼 미존재 | 코드에서 해당 필드 제거 |
| Capacity 파싱 실패 | LLM 할당량 초과 | Regex Fallback 추가 |
| 수동 데이터 덮어쓰기 | LLM이 기본값 반환 | Data Preservation 로직 추가 |

### 알려진 제한사항

| 항목 | 상태 | 대응 계획 |
|------|------|----------|
| 네이버 지도 IP 차단 | ⚠️ 주의 필요 | Proxy 또는 Stealth Plugin 검토 |
| 비숫자 business_id | 일부 수동 등록 필요 | 수동 ID 확보 후 처리 |
| Gemini Rate Limit | 15 RPM 제한 | 배치 처리 + Fallback |

---

## 8. 변경 이력

| 날짜 | 변경 내용 | 담당 |
|------|----------|------|
| 2026-01-23 | Phase 1 완료: GraphQL 크롤러, LLM 파서 구현 | - |
| 2026-01-24 | Phase 2 완료: Supabase 연동, DTO 확장 | - |
| 2026-01-28 | Phase 3 시작: 전국 수집 확장, 데이터 보존 로직 | - |
| 2026-01-29 | 병렬 수집 + 데이터 보존 로직 구현 완료 | - |
