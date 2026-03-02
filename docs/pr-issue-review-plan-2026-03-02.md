# PR/이슈 통합 리뷰 및 개선 계획 (2026-03-02)

## 1) 리뷰 범위
- 기준 브랜치: `origin/dev...feat/197-graphql-business-fields`
- 포함 커밋: `4403377` ~ `ae474ee` (총 10개)
- 포함 이슈 태그: `#197`, `#198`, `#199`, `#200`
- 비고: 과거 전체 저장소 PR 전체가 아니라, **현재 작업 브랜치에 포함된 PR/이슈 연계 변경분** 기준으로 분석

## 2) 전체 요약
- 현재 브랜치는 GraphQL 수집 필드 확장, Apollo 상태 enrich, 파서 컨텍스트 개선, 구조화 필드 우선 로직 강화, 운영 스크립트 추가까지 포함한 대형 변경입니다.
- 신규/추가 테스트 16개는 통과했습니다.
- 다만 운영 데이터 정확도에 영향을 줄 수 있는 우선 수정 항목 2건이 남아 있습니다.

## 3) PR/이슈별 리뷰

### #197 (GraphQL business 필드 확장 + 이슈 템플릿 문서 보정)
- 주요 작업
  - `business` 쿼리에 `desc`, `addressJson`, `phoneInformationJson`, `placeScheduleJson`, `extraDescJson`, `additionalPropertyJson`, `eventDescJson` 추가
  - 이슈 작성 컨벤션 문서(`convention.md`) 구조 보정
- 확인 결과
  - 수집 범위 확장 목적은 달성됨
  - 테스트로 필드 포함 여부 검증됨 (`tests/crawler/test_naver_room_fetcher_graphql_fields.py`)
- 미흡/리스크
  - 해당 이슈 자체의 치명 결함은 없음
  - 다만 후속 로직에서 일부 필드를 충분히 활용하지 못하는 구간이 존재(아래 #198, 후속 커밋 이슈 참고)

### #198 (GraphQL bizItems 필드 확장)
- 주요 작업
  - `bizItems` 쿼리에 `stock`, `price`, `min/maxBookingCount`, `bookingTimeUnitCode`, `min/maxBookingTime`, `isOnsitePayment`, `bookingCountSettingJson`, `extraFeeSettingJson`, `extraDescJson` 추가
- 확인 결과
  - 구조화 데이터 확보 폭이 넓어졌고, 이후 서비스 로직에서 일부 우선 활용하도록 개선됨
- 미흡/리스크
  - `bookingCountSettingJson`가 문자열 JSON인 경우 1시간 예약 가능 추론 누락 가능
  - 근거: `app/services/room_collection_service.py:338`~`346`에서 `dict`만 처리
- 왜 고쳐야 하나
  - 실제 응답이 문자열 JSON일 때 `can_reserve_one_hour`가 구조화 판단 대신 파서/기존값으로 떨어져 데이터 일관성이 깨질 수 있음

### #199 (LLM 파싱 시 business.desc 컨텍스트 전달)
- 주요 작업
  - 수집 서비스에서 `business_desc`를 배치 파싱 아이템에 주입
  - 배치 프롬프트에 `Business Context` 섹션 추가
- 확인 결과
  - 컨텍스트 주입 경로와 프롬프트 포함 여부 테스트 완료
  - 관련 파일: `app/services/room_collection_service.py`, `app/services/room_parser_service.py`
- 미흡/리스크
  - 컨텍스트 품질 자체(노이즈, 과도 길이) 제어는 최소 수준이며, 효과 측정은 운영 스크립트 의존
- 왜 고쳐야 하나
  - 컨텍스트가 과도하거나 잡음이 많으면 파싱 편향/환각 위험이 증가하므로 길이 제한/키워드 요약 전략이 있으면 안정성이 더 높아짐

### #200 (Apollo State 확장 수집: PlaceDetail, BookingBusiness)
- 주요 작업
  - `window.__APOLLO_STATE__`에서 `PlaceSummary` 외 `PlaceDetail`, `BookingBusiness`도 수집해 병합
- 확인 결과
  - enrich prefix 포함 여부 테스트 완료
  - 관련 파일: `app/crawler/naver_map_crawler.py`
- 미흡/리스크
  - 현재 수집된 enrich 데이터가 후단 저장/활용으로 충분히 연결되지는 않음(주로 식별/보조용)
- 왜 고쳐야 하나
  - 수집 비용 대비 활용률이 낮으면 유지보수 비용만 증가하므로, 실제 활용 필드를 명확히 정의해 저장/의사결정에 연결할 필요가 있음

### 후속 하드닝 커밋 (74649be, 50f6707, 09e73cb, b99380a, ae474ee)
- 주요 작업
  - 테스트 보강(16개)
  - 운영 스크립트 추가(`evaluate_parser_against_crawled.py`, `reparse_flagged_rooms.py`)
  - 구조화 우선 fallback 로직 강화(예약 가능/추가요금/당일전화/텍스트 capacity 신호)
  - 파서 안정성 저하 시 프로세스 내 graceful fallback 처리
- 확인 결과
  - 전체 방향성은 적절하고 회귀 방지 테스트가 잘 추가됨
- 미흡/리스크 (우선순위 높음)
  1. `extra_charge` 오탐 가능성
     - 근거: `app/services/room_collection_service.py:361`~`390`
     - `"amount"` 키를 넓게 허용하여 `base.amount` 같은 일반 금액을 추가요금으로 오인 가능
  2. `bookingCountSettingJson` 문자열 JSON 미파싱
     - 근거: `app/services/room_collection_service.py:338`~`346`
     - `dict` 외 문자열(JSON text) 미지원

## 4) 무엇을 했는지 (완료 작업 체크)
- [x] GraphQL `business`/`bizItems` 필드 확장
- [x] Apollo state enrich 수집 로직 반영
- [x] 배치 파서에 business context 전달
- [x] 구조화 필드 우선 fallback 로직 추가
- [x] 보고/복구 운영 스크립트 3종 추가
- [x] 관련 테스트 16개 추가 및 통과

## 5) 어디가 미흡한지 + 왜 수정해야 하는지

### A. 추가요금 판별 정확도 (우선순위 P0)
- 미흡
  - `extraFeeSettingJson` 탐색 시 `"amount"`만 있어도 추출해버려 오탐 가능
- 왜 수정
  - 잘못된 `extra_charge` 저장은 가격 정책/추천 인원 범위 계산까지 연쇄 오염
  - 운영 데이터 신뢰도 직접 훼손

### B. 구조화 예약시간 파싱 일관성 (우선순위 P1)
- 미흡
  - `bookingCountSettingJson` 문자열 JSON을 파싱하지 않음
- 왜 수정
  - 공급 데이터 포맷 변동 시 판단 누락으로 `can_reserve_one_hour` 품질 저하

### C. 컨텍스트/Enrich 활용도 관리 (우선순위 P2)
- 미흡
  - 수집은 확대됐지만 저장/의사결정 활용 명세가 약함
- 왜 수정
  - 유지보수 비용 대비 실효성 확인이 어려워지고, 팀 내 해석 불일치 가능

## 6) 우선순위 기반 개선 계획

### Phase 1 (즉시, 1일)
1. `extra_charge` 추출 키 정책 축소
   - `"amount"` 단독 힌트 제거
   - `extra|additional|surcharge` 문맥 동시 존재 시에만 금액 채택
2. 회귀 테스트 추가
   - `base.amount` + `extraCharge` 공존 시 `extraCharge`만 채택하는 케이스

### Phase 2 (단기, 1일)
1. `bookingCountSettingJson` 문자열 JSON 파싱 지원
2. 회귀 테스트 추가
   - 문자열 JSON 입력에서 `can_reserve_one_hour` 정확히 계산되는 케이스

### Phase 3 (단기, 1~2일)
1. `business context` 길이 제한/정규화 정책 추가
2. `evaluate_parser_against_crawled.py` 리포트를 CI artifact 또는 정기 리포트로 고정

## 7) 검증 기록
- 실행 명령:
  - `python -m pytest -q tests/crawler/test_naver_map_crawler_apollo_enrichment.py tests/crawler/test_naver_room_fetcher_graphql_fields.py tests/services/test_room_collection_business_context.py tests/services/test_room_collection_structured_priority.py tests/services/test_room_parser_batch_context.py tests/integration/test_room_collection_reporting.py`
- 결과:
  - 16 passed, 0 failed

## 8) 결론
- 현재 브랜치는 기능 확장과 안정화 방향이 맞고, 테스트 기반도 확보되었습니다.
- 다만 데이터 정확도 핵심인 `extra_charge` 판별과 구조화 JSON 파싱 일관성은 PR 머지 전에 정리하는 것이 안전합니다.
