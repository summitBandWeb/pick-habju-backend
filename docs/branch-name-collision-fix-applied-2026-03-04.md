# Branch Name Collision Fix Applied (2026-03-04)

## Summary
- target_count: 41
- candidate_ready_count: 41
- applied_count: 41
- verified_count: 41
- verified_match_count: 41
- verified_still_collided_count: 0
- unresolved_count: 0

## Evidence
- apply log: `logs/branch_name_collision_fix_applied_2026-03-04.json`
- applied csv: `docs/branch-name-collision-fix-applied-2026-03-04.csv`

## Notes
- Exact room-name == branch-name collisions were removed for all 41 targets.
- Substring containment can still appear for semantically valid names (e.g., branch includes a generic token like "dev").
