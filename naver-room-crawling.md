# 네이버 합주실 데이터 수집 시스템

## 1. 개요

### 1.1 문제 정의

> **핵심 Pain Point**: 밴드 연습실을 찾는 사용자들은 여러 플랫폼(네이버 지도, 각 합주실 홈페이지, 전화 문의)을 오가며 정보를 수집해야 합니다.

| 단계 | 현재 방식 | 문제점 |
|------|----------|--------|
| 탐색 | 네이버 지도에서 "합주실" 검색 | 지역별 반복 검색 필요 |
| 정보 확인 | 각 합주실 상세페이지 방문 | 룸 정보가 일관되지 않음 |
| 예약 확인 | 네이버 예약 또는 전화 문의 | 실시간 확인 불가 |
| 결정 | 가격/위치/시간 종합 판단 | 정보가 흩어져 있음 |

### 1.2 핵심 가치 제안

```
[ 분산된 합주실 정보 ]  ──▶  [ Pick 합주 통합 DB ]  ──▶  [ 사용자: 한 곳에서 비교/예약 ]
```

### 1.3 수집 대상 데이터

- **기본 정보**: 합주실명, 지점명, 위치(좌표), 주소
- **룸 정보**: 이름, 가격, 수용인원, 이미지
- **예약 메타**: 1시간 단위 예약 가능 여부, 당일 예약 정책

---

## 2. 시스템 아키텍처

### 2.1 전체 워크플로우

```
┌────────────────┐     ┌────────────────┐     ┌────────────────┐     ┌────────────────┐
│ 1. 합주실 탐색  │ ──▶ │ 2. ID 추출     │ ──▶ │ 3. 상세 크롤링  │ ──▶ │ 4. DB 저장     │
│ (네이버 지도)   │     │ (business_id)  │     │ (GraphQL API)  │     │ (Supabase)     │
└────────────────┘     └────────────────┘     └────────────────┘     └────────────────┘
```

### 2.2 목표 아키텍처 (TO-BE)

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           목표 시스템 (TO-BE)                                │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   ┌────────────────┐     ┌────────────────┐     ┌────────────────┐         │
│   │ 네이버 지도     │ ──▶ │ RoomFetcher    │ ──▶ │ RoomParser     │         │
│   │ (Playwright)   │     │ (GraphQL)      │     │ (LLM+Regex)    │         │
│   └────────────────┘     └────────┬───────┘     └────────┬───────┘         │
│                                   │                       │                 │
│                                   ▼                       ▼                 │
│                          ┌────────────────────────────────────┐            │
│                          │         Supabase DB                │            │
│                          │  (branch, room, room_image)        │            │
│                          └───────────────────┬────────────────┘            │
│                                              │                              │
│                                              ▼                              │
│   ┌────────────────┐     ┌────────────────┐     ┌────────────────┐         │
│   │ room_loader.py │ ──▶ │ API Router     │ ──▶ │ NaverCrawler   │         │
│   │ (DB 조회)       │     │ (FastAPI)      │     │ (예약 확인)     │         │
│   └────────────────┘     └────────────────┘     └────────────────┘         │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 3. 구현 상세

### 3.1 합주실 목록 탐색 (Step 1)

#### 방법 선택

| 방법 | 결론 | 사유 |
|------|------|------|
| 네이버 지도 GraphQL | ❌ 불가 | Rate limit, 스키마 비공개 |
| 네이버 예약 GraphQL | ❌ 불가 | 검색 기능 없음 |
| **브라우저 자동화** | ✅ 채택 | Playwright로 실제 동작 확인됨 |

#### 구현: Playwright로 business_id 추출

```python
from playwright.sync_api import sync_playwright

def extract_business_ids(query="합주실"):
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        url = f"https://pcmap.place.naver.com/place/list?query={query}&display=70"
        page.goto(url)
        page.wait_for_load_state("networkidle")

        results = page.evaluate("""
            () => {
                const state = window.__APOLLO_STATE__;
                const places = [];
                for (const key in state) {
                    if (key.startsWith('PlaceSummary:')) {
                        places.push({
                            id: key.split(':')[1],
                            name: state[key].name
                        });
                    }
                }
                return places;
            }
        """)
        browser.close()
        return results
```

### 3.2 상세 정보 크롤링 (Step 2)

#### API 정보

| 항목 | 값 |
|------|-----|
| URL | `https://booking.naver.com/graphql` |
| Method | `POST` |
| Content-Type | `application/json` |

#### 필요한 쿼리

| 쿼리 | 용도 |
|------|------|
| `bizItems` | 룸 목록 (이름, 가격, 이미지) |
| `business` | 지점 정보 (이름, 좌표) |

> ⚠️ **주의**: `projections: "MIN_MAX_PRICE,RESOURCE"` 없이 요청하면 가격과 이미지가 `null`로 반환됩니다!

### 3.3 LLM 전처리 (Step 3)

#### 파싱 대상 필드

| 필드 | 입력 예시 | 출력 |
|------|----------|------|
| `clean_name` | `"[평일] 블랙룸"` | `"블랙룸"` |
| `day_type` | `"[주말/공휴일] 화이트룸"` | `"weekend"` |
| `max_capacity` | `"최대 10명 수용"` | `10` |
| `recommend_capacity` | `"4~6인 권장"` | `5` |
| `extra_charge` | `"인당 3000원 추가"` | `3000` |
| `requires_call_on_same_day` | `"당일 예약은 전화"` | `true` |

#### 구현: Gemini LLM + Regex Fallback

```python
class RoomParserService:
    def __init__(self):
        genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
        self.model = genai.GenerativeModel('gemini-2.0-flash')

    async def parse_room_desc(self, name: str, desc: str) -> Dict:
        try:
            response = await self.model.generate_content(prompt)
            await asyncio.sleep(4)  # Rate limiting (15 RPM)
            return json.loads(response.text)
        except Exception:
            return self._parse_with_regex(name, desc)

    def _parse_with_regex(self, name: str, desc: str) -> Dict:
        # Fallback: 정규식으로 파싱
        max_match = re.search(r'(?:최대|max|MAX)\s*(\d+)', desc, re.IGNORECASE)
        # ...
```

---

## 4. DB 스키마

### 4.1 테이블 구조

```sql
-- branch: 합주실 지점
CREATE TABLE branch (
    business_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    coordinates FLOAT[],
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- room: 개별 룸
CREATE TABLE room (
    business_id TEXT REFERENCES branch(business_id),
    biz_item_id TEXT,
    name TEXT NOT NULL,
    price_per_hour INTEGER,
    max_capacity INTEGER,
    recommend_capacity INTEGER,
    PRIMARY KEY (business_id, biz_item_id)
);

-- room_image: 룸 이미지 (JSONB 배열)
CREATE TABLE room_image (
    business_id TEXT,
    biz_item_id TEXT,
    image_url JSONB,  -- ["url1", "url2", ...]
    PRIMARY KEY (business_id, biz_item_id)
);
```

### 4.2 DTO 구조

```python
class RoomKey(BaseModel):
    name: str
    branch: str
    business_id: str
    biz_item_id: str
    price_per_hour: Optional[int] = None
    max_capacity: Optional[int] = None
    recommend_capacity: Optional[int] = None
    image_urls: Optional[List[str]] = None
```

---

## 5. 구현 로드맵

### Phase 1: 데이터 수집 인프라 ✅ 완료

| 작업 | 상태 | 파일 |
|------|------|------|
| DB 테이블 생성 | ✅ | Supabase 대시보드 |
| 네이버 지도 크롤러 | ⏸️ 보류 | `naver_map_crawler.py` |
| 상세 정보 크롤러 | ✅ | `naver_room_fetcher.py` |
| LLM 파서 | ✅ | `room_parser_service.py` |

### Phase 2: 시스템 연동 ✅ 완료

| 작업 | 상태 | 파일 |
|------|------|------|
| Supabase 클라이언트 | ✅ | `database.py` |
| Room Repository | ✅ | `room_repository.py` |
| room_loader 수정 | ✅ | `room_loader.py` |
| DTO 확장 | ✅ | `dto.py` |

### Phase 3: 운영 자동화 🚧 진행 중

| 작업 | 상태 | 비고 |
|------|------|------|
| Batch Processing | ✅ | LLM 요청 최적화 |
| Rate Limiting | ✅ | Gemini 15 RPM 준수 |
| Regex Fallback | ✅ | LLM 실패 시 대체 |
| 스케줄러 | ⏳ | 주기적 크롤링 |
| 알림 서비스 | ⏳ | Discord Webhook |

---

## 6. 이슈 및 해결

### 6.1 해결된 이슈

| 이슈 | 원인 | 해결 |
|------|------|------|
| GraphQL 필드 오류 | `roadAddress`, `phone` 미존재 | 쿼리에서 제거 |
| coordinates 형식 | 배열 `[lng, lat]` 반환 | 객체로 변환 처리 |
| Gemini 모델 404 | `1.5-flash` 지원 중단 | `2.0-flash`로 변경 |
| room_image 중복키 | PK 구조 다름 | JSONB 배열 방식 |
| Capacity 파싱 실패 | LLM 할당량 초과 | Regex Fallback 추가 |

### 6.2 보류된 이슈

| 이슈 | 사유 | 해결 계획 |
|------|------|----------|
| 네이버 지도 IP 차단 | Playwright 감지 | Phase 3에서 Proxy/Stealth 적용 |
| 비숫자 business_id | `sadang`, `dream_sadang` | 수동 네이버 ID 확보 |

---

## 7. 파일 구조

```
app/
├── core/
│   └── database.py              # Supabase 클라이언트
├── crawler/
│   ├── naver_map_crawler.py     # 지도 검색 (⏸️ 보류)
│   └── naver_room_fetcher.py    # GraphQL 크롤러 ✅
├── repositories/
│   └── room_repository.py       # DB 조회 ✅
├── services/
│   └── room_parser_service.py   # LLM + Regex 파서 ✅
├── utils/
│   └── room_loader.py           # DB 기반 로더 ✅
└── models/
    └── dto.py                   # 확장된 DTO ✅

scripts/
└── update_room_db.py            # DB 업데이트 스크립트

migrations/
└── 001_create_room_tables.sql   # 스키마 참고용
```

---

## 8. API 문서

Swagger UI: `/docs`
ReDoc: `/redoc`

---

## 9. 변경 이력

| 날짜 | 변경 내용 |
|------|----------|
| 2026-01-23 | Phase 1 완료: GraphQL 크롤러, LLM 파서 |
| 2026-01-24 | Phase 2 완료: DB 연동, DTO 확장 |
| 2026-01-24 | room_parser_service 개선: Rate limiting, Regex 패턴 확장 |
| 2026-01-24 | Swagger UI 도입 (별도 이슈 #110) |
