# Priority Lat/Lng Backfill Applied (2026-03-03)

## Why
- Frontend map marker issues were traced to missing `branch.lat/lng` values in priority-area branches.
- API path (`room_loader -> availability`) was working, but many rows had null coordinates.

## Scope
- Target set: priority-area allowlist business IDs.
- Column scope: `branch.lat`, `branch.lng` only.
- Method:
  - Re-fetch `business.coordinates` via Naver Booking GraphQL
  - Normalize coordinate order (swap when latitude/longitude appear reversed)
  - Update branch row by `business_id`

## Result
- Initial missing in allowlist: `16`
- Targeted Naver IDs: `16`
- Updated: `16`
- Unresolved: `0`
- Post-check missing in allowlist: `0`

## Evidence
- Applied log:
  - `logs/priority_latlng_backfill_applied_2026-03-03.json`

## Note
- One row has floating precision difference on verification, but persisted values are 정상 범위 좌표.
