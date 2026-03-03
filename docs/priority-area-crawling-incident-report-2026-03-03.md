# 우선지역 크롤링/검색 노출 이슈 종합 리포트 (2026-03-03)

## 1. 사건 개요
- 제보 시점(2026-03-03):
  - 07:42: "합주실의 좌표가 전부 null"
  - 10:47: "이수역 기준 검색 시 `그루브합주실 사당점`만 노출"
  - 11:19~11:24: "작업 전에는 더 많이 보였는데, 변경 후 1~2개만 보임"
- 최종 결론:
  - 단일 원인이 아니라, `당일 연락 필터 + 지도 박스 범위 + branch/room 데이터 불일치 + place 성격 ID 혼입`이 겹친 복합 이슈.

## 2. 이번 세션에서 확인한 사실
### 2.1 좌표 null 자체는 현재 핵심 원인이 아님
- DB 확인 결과, 다수 지점은 좌표(lat/lng)가 존재.
- 프론트 제보의 "과거엔 대부분 null"은 맞았으나, 현재 "2개만 노출" 현상은 좌표 null 하나로 설명되지 않음.

### 2.2 API 재현 결과 (실측)
- 2026-03-03(당일) 요청:
  - 응답에 사실상 `sadang(그루브)` 위주로 축소됨.
  - 예시 응답: `available_biz_item_ids = ["13","14"]`.
- 2026-03-04(익일) 요청:
  - `dream_sadang` + `sadang` 노출.
  - 예시 응답: `available_biz_item_ids = ["25","26","27","28","13","14","16"]`.

### 2.3 좁은 박스(BBox) 영향 존재
- 이수/사당 중심 박스에서 동쪽 경계가 좁으면 일부 지점(예: 비쥬 계열)이 잘림.
- 동쪽 경계를 넓히면(예: `neLng` 확장) 추가 지점이 다시 노출되는 케이스 확인.

### 2.4 branch 대비 room 데이터 부족이 큼
- 세션 중 점검 수치:
  - `branch_total = 247`
  - `branch_with_room = 85`
  - `branch_without_room = 162`
- 즉, branch에 지점이 있어도 room이 없으면 검색 응답에 못 뜨는 구조.

### 2.5 "requiresContactOnSameDay=True이면 제외"의 정확한 의미
- 의미: **룸 단위 제외**.
- 당일 요청에서 `requiresContactOnSameDay=True`인데 `phoneNumber`가 없으면 해당 룸을 서버가 제외.
- 결과적으로 한 지점의 룸이 전부 걸러지면, 사용자 입장에서는 지점 자체가 사라진 것처럼 보임.

## 3. 사용자 질문별 정리
### Q1. "전화번호 없으면 합주실 자체를 제외하나요?"
- 정확히는 룸을 제외함.
- 다만 해당 지점의 룸이 모두 제외되면 지점도 응답에서 사라짐.

### Q2. "그럼 전화번호 없는 다른 지점도 다 사라져야 하는 것 아닌가요?"
- `requiresContactOnSameDay=True` 조건이 붙은 룸에만 해당.
- 같은 전화번호 null이어도 룸 정책 플래그가 다르면 제외/유지가 갈림.

### Q3. "왜 이수/사당에서 2개만 뜨나요?"
- 복합 원인:
  - 당일 필터로 일부 룸 제외,
  - 좁은 BBox로 일부 지점 제외,
  - branch는 있는데 room/fetch_full_info가 비어있는 지점 다수.

## 4. 코드 레벨 원인 근거
### 4.1 당일 연락 필터
- `app/services/availability_service.py`:
  - `needs_today_contact` 계산: 515행
  - 당일 + 전화번호 없으면 제외: 530행
  - 1시간 예약 연락 필터: 514, 521행
  - 슬롯 계산 시 `hour_slots[:-1]` 사용: 226, 295행

### 4.2 place 성격 ID 혼입 가능성
- 과거 로직에서 `bookingBusinessId`가 없으면 `placeId`를 `id`로 쓰는 fallback이 있어 비예약 대상 혼입 가능.
- 본 세션에서 수정:
  - `app/crawler/naver_map_crawler.py:218` `id: place.bookingBusinessId ?? null`
  - `app/crawler/naver_map_crawler.py:219` `bookingBusinessId` 명시
  - `app/crawler/naver_map_crawler.py:278` non-bookable item skip 로그 추가

### 4.3 branch 삭제 시 room 연쇄 삭제 가능성
- `migrations/001_create_room_tables.sql:43`:
  - `room.business_id -> branch.business_id` FK가 `ON DELETE CASCADE`.
- 정리 작업 시 branch를 삭제하면 room이 같이 삭제될 수 있음.

## 5. 이번 세션에서 실제 반영한 수정
### 5.1 place 성격 ID 수집 차단 (핵심)
- 파일: `app/crawler/naver_map_crawler.py`
- 변경:
  - `placeId` fallback 제거.
  - `bookingBusinessId` 없는 항목은 merge 단계에서 제외.

### 5.2 수집 리포트에 비예약 제외 수치 추가
- 파일: `app/services/room_collection_service.py`
- 변경:
  - `bookingBusinessId` 불일치/누락 항목 제외.
  - `query_reports`에 `excluded_non_bookable` 필드 추가.

### 5.3 테스트 보강/수정
- 파일:
  - `tests/crawler/test_naver_map_crawler.py`
  - `tests/integration/test_room_collection_reporting.py`
  - `tests/integration/test_room_collection_flow.py`
- 변경:
  - 테스트 fixture에 `bookingBusinessId`를 넣어 새 정책 반영.

### 5.4 좌표 동기화 스크립트 보강(로컬)
- 파일: `scripts/update_seoul_coordinates.py`
- 내용:
  - place 성격 ID 차단,
  - 룸 없는 비예약 사업장 차단,
  - 좌표 업데이트 전에 예약 가능성 검증.
- 참고:
  - 해당 `scripts/` 경로는 현재 `.gitignore` 대상이라 Git 변경 목록에는 잡히지 않음.

## 6. 검증 결과
- 실행 명령:
  - `python -m pytest tests/crawler/test_naver_map_crawler.py tests/integration/test_room_collection_reporting.py tests/integration/test_room_collection_flow.py -q`
- 결과:
  - `20 passed`
  - 경고는 있었으나 실패 없음.

## 7. 운영 반영 권장안
### 7.1 데이터 정리
- branch에만 있고 room이 없는 지점 리스트를 먼저 추출.
- 비예약(place 성격) ID와 예약 가능 ID를 분리 관리.
- branch 대량 정리 시 FK cascade 영향(룸 삭제)을 반드시 사전 검토.

### 7.2 재수집 순서
1. place ID 차단 로직 적용된 수집기로 우선지역 재수집.
2. `fetch_full_info` 성공 + room 존재 지점만 프로덕션 branch로 반영.
3. 이수/사당 박스 기준 API 스모크 테스트(당일/익일 각각) 수행.

### 7.3 모니터링
- `query_reports.excluded_non_bookable` 지표 추적.
- `branch_without_room` 비율 추적.
- 당일 필터(`requiresContactOnSameDay`)로 제거된 룸 수 추적.

## 8. 최종 결론
- 2026-03-03 이슈는 "좌표 null" 단독 이슈가 아니라 데이터/필터/경계/ID 품질이 겹친 복합 장애였다.
- 이번 세션에서 우선 차단해야 할 항목인 `place 성격 ID 수집`은 코드로 차단 완료.
- 남은 핵심 운영 과제는 `branch-room 정합성 복구`와 `재수집 파이프라인 안정화`다.

---

## 2026-03-03 전화번호 누락 대응 상세 기록
- 이번 세션의 전체 작업 내역(원인 분석, 코드 수정, 테스트 결과)은 아래 문서에 정리했습니다.
- [docs/phone-number-crawling-fix-report-2026-03-03.md](./phone-number-crawling-fix-report-2026-03-03.md)
