# Room Name Safe DB Refresh Applied (2026-03-03)

## Policy
- Scope: 6 priority-area audit set only.
- Column scope: `room.name` only.
- Do not touch capacity/price/metadata columns.
- Apply only when all are true:
  - `biz_item_id` overlaps with existing DB row.
  - Parsed `clean_name` is non-empty and differs from noisy raw name.
  - Existing DB `name` equals audit raw name (or normalizes to the same clean value).
  - No conflicting curated DB name.

## Dry Run
- Source audit rows: `191`
- DB overlap rows: `174`
- Name-clean candidates from audit: `60`
- Eligible updates after safety filter: `49`
- Conflicts skipped: `0`
- Missing DB row skipped: `11`

## Applied Result
- Target updates: `49`
- Applied: `49`
- Verified after update: `49/49`
- Failed: `0`

## Effect Check
- Post-check on overlap set (`174` rows):
  - `room.name` still noisy by cleaner heuristic: `0`

## Evidence
- Dry-run log:
  - `logs/room_name_safe_db_refresh_dry_run_2026-03-03.json`
- Applied log:
  - `logs/room_name_safe_db_refresh_applied_2026-03-03.json`
- Parser/test changes used for this refresh:
  - `app/services/room_parser_service.py`
  - `app/services/room_collection_service.py`
  - `tests/services/test_room_parser_service.py`
  - `tests/services/test_room_collection_service.py`
