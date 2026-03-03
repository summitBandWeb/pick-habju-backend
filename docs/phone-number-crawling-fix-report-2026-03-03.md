# 전화번호 누락 이슈 작업 기록 (2026-03-03)

## 1. 문서 목적
- 이 문서는 본 대화 세션에서 수행한 **전화번호 누락 이슈 분석/수정/검증** 작업을 전체 기록으로 남기기 위한 문서입니다.
- 대상 시스템: `pick-habju-backend` 크롤링 및 수집 파이프라인

## 2. 사용자 제보 요약
- 제보 내용: “합주실 상세에는 전화번호가 있는데, 왜 수집이 안 되는지 확인하고 수정해달라.”
- 첨부 화면 예시: `0507-1343-7985` 형태의 대표번호가 상세 페이지에 노출됨.

## 3. 조사 과정 요약

### 3.1 코드/로그 점검
- 전화번호 저장 경로 점검:
  - `app/services/room_collection_service.py`
  - `_extract_business_phone_number`
  - `_extract_phone_number_from_payload`
  - `_save_to_db`의 `branch.phone_number` upsert
- 기존 테스트 점검:
  - `tests/services/test_room_collection_service.py`의 business/room phone fallback 케이스 확인

### 3.2 실증 확인 (GraphQL 스모크)
- 실행:
  - `python scripts/naver_graphql_smoke_with_state.py --business-id 522011 --state logs/naver_storage_state.json`
- 결과:
  - `business` 쿼리: `{"data":{"business":null}}`
  - `bizItems` 쿼리: 정상 응답(200) + 룸 상세 텍스트 반환
- 의미:
  - 실제 운영 구간에서 `business.phoneInformationJson`이 빈 경우가 빈번할 수 있으며, 이 경우 기존 로직은 전화번호를 놓치기 쉬움.

### 3.3 로그 단서
- `logs/app.log` / `logs/app.log.2026-03-02`에서 반복 확인:
  - `Business query returned null; using fallback business payload ...`
  - `GraphQL ... rate-limited (429) ...`
- 의미:
  - 전화번호 원천을 `business` 응답에만 의존하면 누락이 발생할 수 있는 구조.

## 4. 원인 분석

### 원인 1: business 쿼리 null 구간 존재
- `business` 응답이 `null`일 때 fallback business payload에는 전화번호가 없음.

### 원인 2: fallback 탐색 범위 부족
- 기존은 `business.phone*`, `room.phone*` 중심 탐색.
- 실제 번호가 `bookingPrecautionJson.desc`, `extraDescJson`, `desc` 텍스트에만 존재하는 케이스를 충분히 커버하지 못함.

### 원인 3: 번호 추출 정규식/우선순위 한계
- 계좌번호/긴 숫자열과 혼재된 텍스트에서 전화번호 판별이 약함.
- `0507` 타입 번호 처리에서 우선순위/길이 조건 미세 이슈 확인 후 보완 필요.

## 5. 적용한 수정 사항

## 5.1 수집 힌트(source item) 연계
- 파일: `app/services/room_collection_service.py`
- 변경:
  - `self._source_item_hints` 캐시 추가
  - `_collect_items`에서 `business_id -> map item` 저장
  - `collect_by_id`에서 source hint 조회 후 `_save_to_db(..., source_hint=...)` 전달
- 효과:
  - business/room payload에 번호가 없을 때도 지도 검색 단계의 번호를 fallback으로 활용 가능

### 5.2 전화번호 추출 경로 확장
- 파일: `app/services/room_collection_service.py`
- 변경:
  - `_extract_business_phone_number` 시그니처 확장:
    - `source_hint` 인자 추가
  - 탐색 후보 확장:
    - `business` 전체 payload
    - `source_hint` 전체 payload
    - room의 `bookingPrecautionJson`, `extraDescJson`, `desc`, room 전체 payload
- 효과:
  - 전화번호가 구조화 필드가 아닌 텍스트에만 존재해도 추출 가능

### 5.3 전화번호 정규식/스코어링 개선
- 파일: `app/services/room_collection_service.py`
- 변경:
  - `_extract_phone_number_from_text`를 한국 전화번호 중심으로 보강
  - `0507`, `02`, `010`, 지역번호, 대표번호(15xx/16xx 등) 우선
  - 주변 키워드(`전화`, `문의`, `contact`, `phone`) 기반 가중치 추가
  - 허용 자릿수 조정(최대 12) 및 `+82` 정규화
- 효과:
  - 계좌번호 등 숫자열 혼입 상황에서 전화번호 선택 정확도 개선

## 6. 테스트 추가/변경

### 파일
- `tests/services/test_room_collection_service.py`

### 추가 케이스
1. `bookingPrecautionJson.desc` 텍스트에서 번호 추출
   - 예시 텍스트: `입금 계좌 3333134566206 / 문의 0507-1343-7985`
   - 기대: `0507-1343-7985` 저장
2. `source_hint`(지도 item) 기반 번호 fallback
   - 기대: `branch.phone_number`에 반영

## 7. 검증 결과

### 7.1 단위/서비스 테스트
- 실행:
  - `python -m pytest -q tests/services/test_room_collection_service.py`
- 결과:
  - `21 passed`

### 7.2 통합 테스트
- 실행:
  - `python -m pytest -q tests/integration/test_room_collection_flow.py tests/integration/test_room_collection_reporting.py`
- 결과:
  - `11 passed`

### 7.3 샘플 데이터 기반 추출 확인
- 실행(간이 검증):
  - `logs/searchBizItem_1384809_full.json`의 `bookingPrecautionJson` 텍스트에서 추출 함수 호출
- 결과:
  - `010-8476-7377` 정상 추출

## 8. 변경 파일 목록 (본 세션 핵심)
- `app/services/room_collection_service.py`
- `tests/services/test_room_collection_service.py`
- `docs/phone-number-crawling-fix-report-2026-03-03.md` (본 문서)

## 9. 운영 반영 후 확인 체크리스트
1. 우선지역 수집 실행:
   - `python scripts/collect_rooms.py --priority-areas`
2. 수집 후 branch 데이터 확인:
   - `branch.phone_number`가 null에서 채워지는지 확인
3. 표본 점검:
   - `business` 쿼리 null 케이스에서도 텍스트/소스힌트 fallback으로 번호가 들어오는지 확인

## 10. 남은 리스크/후속 과제
- `business` GraphQL null/429는 외부 환경(세션/레이트리밋) 영향이 커서 완전 제거 불가.
- 현재는 누락 완화(추출 경로 확장)까지 반영했으며, 장기적으로는 아래 보강 필요:
  - 수집 리포트에 “전화번호 추출 source”(business/room/text/source_hint) 메타 기록
  - 재수집 시 누락 지점만 타겟팅하는 재처리 유틸 강화
