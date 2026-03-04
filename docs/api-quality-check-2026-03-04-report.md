# API Quality Check Report (2026-03-04T01:39:52)

## Matrix
- Total requests: 135
- Dates: 2026-03-05, 2026-03-11, 2026-03-18
- Time ranges: 01:00-03:00, 10:00-12:00, 19:00-21:00
- Capacities: 2, 8, 12
- Areas: 이수, 사당, 홍대입구, 신촌, 서울광역

## Endpoint Snapshot
- `GET /ping`: 200
- `GET /health`: 503
- `GET /api/test/success`: 200
- `GET /api/test/error?status_code=400`: 400
- `GET /api/test/server-error`: 500
- `GET /api/favorites` (missing header): 422
- `GET /api/favorites` (invalid header): 400
- `GET /api/favorites` (valid header): 200

## Availability Quality
- Scope note: 이 섹션의 `HTTP status distribution`과 `Non-200 count`는 availability matrix 135건만 집계하며, `Endpoint Snapshot`의 헬스체크/테스트 엔드포인트는 포함하지 않습니다.
- HTTP status distribution: {'200': 135}
- Transport error count: 0
- Non-200 count: 0
- Envelope invalid count: 0
- `isSuccess == false` count: 0
- `available_biz_item_ids` mismatch requests: 50
- `branch` includes room name count: 833 (request-row occurrences)

## Field Quality
- `phone_number`: null=943, non_null=0, valid_format=0, invalid_format=0
- `display_name`: null=943, non_null=0

## Coverage
- Local union business IDs (이수/사당/홍대입구/신촌): 34
- 서울광역 business IDs: 43
- 서울광역 only business IDs: 9

## Output Files
- Summary JSON: `docs/api-quality-check-2026-03-04-summary.json`
- Mismatch CSV: `docs/api-quality-check-2026-03-04-mismatch.csv`
- Coverage CSV: `docs/api-quality-check-2026-03-04-coverage.csv`
- Branch/Room overlap CSV: `docs/api-quality-check-2026-03-04-branch-room-overlap.csv`
- Markdown report: `docs/api-quality-check-2026-03-04-report.md`

## Why Commit CSV/JSON Artifacts?
- DB를 매번 직접 조회하면 시점마다 결과가 달라질 수 있어, PR 리뷰 시 동일 증적을 재현하기 어렵다.
- 그래서 검증 스크립트의 결과 스냅샷(CSV/JSON)을 함께 커밋해 리뷰어가 동일 데이터로 확인할 수 있게 유지한다.
- 운영 검증 자체는 DB 연동으로 수행하고, 이 파일들은 "검증 결과 증적" 역할만 담당한다.
