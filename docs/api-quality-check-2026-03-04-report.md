# API Quality Check Report (2026-03-04T01:39:52)

## Matrix
- Total requests: 135
- Dates: 2026-03-05, 2026-03-11, 2026-03-18
- Time ranges: 01:00-03:00, 10:00-12:00, 19:00-21:00
- Capacities: 2, 8, 12
- Areas: ?´ìˆ˜, ?¬ë‹¹, ?ë??…êµ¬, ? ì´Œ, ?œìš¸ê´‘ì—­

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
- HTTP status distribution: {'200': 135}
- Transport error count: 0
- Non-200 count: 0
- Envelope invalid count: 0
- `isSuccess == false` count: 0
- `available_biz_item_ids` mismatch requests: 50
- `branch` includes room name count: 833

## Field Quality
- `phone_number`: null=943, non_null=0, valid_format=0, invalid_format=0
- `display_name`: null=943, non_null=0

## Coverage
- Local union business IDs (?´ìˆ˜/?¬ë‹¹/?ë??…êµ¬/? ì´Œ): 34
- ?œìš¸ê´‘ì—­ business IDs: 43
- ?œìš¸ê´‘ì—­ only business IDs: 9

## Output Files
- Summary JSON: `docs/api-quality-check-2026-03-04-summary.json`
- Mismatch CSV: `docs/api-quality-check-2026-03-04-mismatch.csv`
- Coverage CSV: `docs/api-quality-check-2026-03-04-coverage.csv`
- Branch/Room overlap CSV: `docs/api-quality-check-2026-03-04-branch-room-overlap.csv`
- Markdown report: `docs/api-quality-check-2026-03-04-report.md`

