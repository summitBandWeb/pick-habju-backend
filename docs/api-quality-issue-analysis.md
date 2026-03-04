# API 품질 이슈 재분석 (2026-03-04)

아래 내용은 기존 리포트를 재검증해 "진짜 오류"와 "표현 규칙 차이"를 분리한 결과입니다.

## 1. 불일치 50건 재분류

### 기준
- 원본 파일: `docs/api-quality-check-2026-03-04-mismatch.csv` (50건)
- 재분류 원칙:
  - `partial 허용`: `available == false` 이지만 `available_slots`에 `true`가 하나라도 있으면 정상 표현으로 간주
  - `실질 오류`: `id_not_in_rooms` 또는 partial로 설명 불가한 케이스

### 결과
- 전체 mismatch 요청: 50건
- partial-only 요청: 36건
- 실질 오류 요청: 14건
- 실질 오류 ID(중복 포함): 34건
- 실질 오류 ID(유니크): 26개

### 산출물
- 재분류 상세(JSON): `docs/api-quality-check-2026-03-04-real-issues.json`
- 실질 오류 행(CSV): `docs/api-quality-check-2026-03-04-real-issues.csv`

## 2. 커버리지 갭(서울광역 대비) + 흑석/상도 추가 검증

### 기존 4지역 기준(이수/사당/홍대입구/신촌)
- 기준 파일: `docs/api-quality-check-2026-03-04-coverage.csv`
- 서울광역에만 존재하는 business_id: 9개
  - `1314022, 1384809, 1415457, 1500479, 1593535, 247786, 570236, 706413, 759837`

### 흑석/상도 추가 검증(임시 bbox 가정)
- 주의: 프론트 bbox 미정 상태라 검증용 bbox를 임시로 가정함
- 조건: 날짜(+1,+7,+14), 시간(01-03,10-12,19-21), capacity=12
- 결과:
  - 4지역 대비 새로 커버된 ID: `1384809, 570236` (2개)
  - 남은 갭: `1415457, 1500479, 1593535, 759837` (4개)

### 해석
- 흑석/상도를 추가하면 갭이 줄어드는 것은 맞음
- 하지만 "서울광역과 완전 일치"는 아직 아님
- 따라서 6지역 완전 커버 목표라면 흑석/상도 bbox 튜닝 외에 홍대권 경계 재조정(또는 합정권 추가)이 필요함

### 산출물
- `docs/api-quality-check-2026-03-04-coverage-heukseok-sangdo.json`
- `docs/api-quality-check-2026-03-04-coverage-gap.csv`

## 3. branch 이름이 room 이름으로 오염되는 문제

### 관측
- 오버랩 CSV: `docs/api-quality-check-2026-03-04-branch-room-overlap.csv` (82행)
- 해당 business_id: 41개
- DB 직접 대조 결과:
  - `branch.name == room.name` (정확히 동일) business_id: 29개
  - `branch.name`이 어떤 `room.name`을 부분 포함 business_id: 41개
  - 위 29개 중 multi-room 지점(룸 2개 이상 보유) business_id: 25개

### 원인(코드 기준)
- branch 저장 시 이름 결정 로직:
  - `display_name = business.businessDisplayName or business.name or businessId`
  - 위치: `app/services/room_collection_service.py` (`_save_to_db`)
- 즉, Naver Booking의 business 단 이름이 룸 단위 상품명(`A룸`, `S룸`, `ROOM 1`)으로 내려오면,
  branch에도 그대로 저장됨
- API 응답은 `room_detail.branch`(branch table의 `name`)를 그대로 사용
  - 위치: `app/services/availability_service.py`

### 수정 방향(권장)
1. branch canonical name 결정 규칙 추가
   - 룸명 패턴(`A룸`, `S룸`, `N번방`, `X ROOM`)이 branch 후보와 동일하고 room이 2개 이상이면 저신뢰로 분류
2. 저신뢰 branch 후보일 때 대체 우선순위
   - `source_hint.name`(지도 PlaceSummary) -> 기존 DB `branch.name` 유지 -> 마지막 fallback
3. 보정 배치
   - 이미 오염된 41개 business_id 대상 업데이트 스크립트 실행
4. 회귀 방지
   - 수집 파이프라인 테스트에 "branch가 단일 room 상품명으로만 저장되지 않는지" 추가

### 3-1. 41건 별도 정정 실행 결과 (2026-03-04)
- 실행 스크립트: `scripts/fix_branch_name_room_collision.py`
- 대상: `docs/api-quality-check-2026-03-04-branch-room-overlap.csv` 기준 business_id 41개
- 처리 순서: `dry-run -> apply -> verify`
- 적용 결과:
  - target_count: 41
  - candidate_ready_count: 41
  - applied_count: 41
  - verified_match_count: 41
  - verified_still_collided_count: 0 (스크립트의 exact-collision 기준)
  - unresolved_count: 0
- 로그/증적:
  - `logs/branch_name_collision_fix_dry_run_2026-03-04.json`
  - `logs/branch_name_collision_fix_applied_2026-03-04.json`
  - `docs/branch-name-collision-fix-applied-2026-03-04.csv`
  - `docs/branch-name-collision-fix-applied-2026-03-04.md`

## 4. 기타 상태
- `GET /health`는 여전히 `503` (`database: down`)
- `phone_number`, `display_name`은 현재 응답에서 대다수 null이며, 별도 수집 보강 과제로 분리 필요

