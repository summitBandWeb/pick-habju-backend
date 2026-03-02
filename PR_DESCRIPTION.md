# [#197]; feat: 네이버 합주실 크롤링 파이프라인 구조화 우선 고도화

## 0. 도입 배경 (Background)
네이버 합주실 데이터 수집 파이프라인에서 LLM 파싱 정확도 편차와 운영 불안정(모델 메모리 부족, 텍스트 의존 과다)을 줄이기 위해,
GraphQL/Apollo 수집 범위를 확장하고 저장 단계에서 구조화 신호 우선 정책을 도입했습니다.

관련 이슈:
- #197 GraphQL business 필드 확장
- #198 GraphQL bizItems 필드 확장
- #199 business.desc 컨텍스트 주입
- #200 Apollo State 확장 수집

## 1. 주요 변경 사항 (Proposed Changes)
- GraphQL 수집 필드 확장
  - `business`: `desc`, `addressJson`, `phoneInformationJson`, `placeScheduleJson`, `extraDescJson`, `additionalPropertyJson`, `eventDescJson`
  - `bizItems`: `stock`, `min/maxBookingCount`, `min/maxBookingTime`, `bookingTimeUnitCode`, `isOnsitePayment`, `bookingCountSettingJson`, `extraFeeSettingJson`, `extraDescJson`
- Apollo State enrich 확장
  - `PlaceSummary` + `PlaceDetail` + `BookingBusiness` 병합
- LLM 컨텍스트 강화
  - `business.desc`를 배치 파싱 프롬프트 컨텍스트로 주입
- 저장 단계 구조화 우선 정책 강화 (`RoomCollectionService`)
  - `can_reserve_one_hour`: `structured(minBookingTime + bookingTimeUnitCode) > parsed > existing`
  - `max_capacity/recommend_capacity`: 고신뢰 텍스트 패턴(예: `정원 N명, 최대 M명`) 우선 후 parser fallback
  - `requires_call_on_same_day`: 구조화 JSON key/value 신호 우선 + 구조화 텍스트 블록(`extraDescJson[].title/context`) 패턴 감지 후 parser fallback
  - `extra_charge`: `parsed > structured(extraFeeSettingJson) > existing`
- 운영/검증 스크립트 추가
  - `scripts/ensure_ollama_resources.py`
  - `scripts/evaluate_parser_against_crawled.py`
  - `scripts/reparse_flagged_rooms.py`
- 테스트 보강
  - crawler/service/integration/core 테스트 추가 및 구조화 우선 회귀 테스트 추가

## 2. 체크리스트 (Checklist)
- [x] 관련 이슈를 PR 커밋 메시지 또는 본문에 명시했습니다. (`#197`, `#198`, `#199`, `#200`)
- [x] PR 제목은 `[#이슈번호]; <태그>: <설명>` 컨벤션을 준수했습니다.
- [x] 신규 작성 함수/메서드는 필요한 docstring/주석을 포함했습니다.
- [x] 테스트 코드를 작성했거나 기능 테스트를 완료했습니다.

실행한 테스트:
- `python -m pytest -q tests/core/test_ollama_client.py tests/crawler/test_naver_map_crawler_apollo_enrichment.py tests/crawler/test_naver_room_fetcher_graphql_fields.py tests/services/test_room_collection_business_context.py tests/services/test_room_collection_structured_priority.py tests/services/test_room_parser_batch_context.py tests/integration/test_room_collection_reporting.py`
- 결과: `18 passed`

추가 실행:
- `python -m pytest -q tests/services/test_room_collection_structured_priority.py tests/services/test_room_collection_service.py`
- 결과: `25 passed`

## 3. 참고 자료 (Optional)
- 파서/크롤링 비교 리포트는 로컬 검증 스크립트로 생성 가능:
  - `python scripts/evaluate_parser_against_crawled.py --business-id 522011 --model llama3.2:3b`
- Ollama 리소스 점검:
  - `python scripts/ensure_ollama_resources.py --primary llama3.1:8b --fallback llama3.2:3b`

## 영향 범위
- `app/crawler/naver_room_fetcher.py`
- `app/crawler/naver_map_crawler.py`
- `app/services/room_collection_service.py`
- `app/services/room_parser_service.py`
- `app/core/ollama_client.py`
- `scripts/*` (운영/검증)
- `tests/*` (보강)

## 롤백 전략
- 구조화 우선 판단 로직은 `RoomCollectionService` 내부에 국한되어 있어,
  문제가 발생하면 해당 우선순위 블록만 parser-first 정책으로 즉시 복귀 가능합니다.
