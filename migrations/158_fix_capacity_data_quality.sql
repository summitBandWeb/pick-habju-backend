-- Migration 158: capacity 필드 이상값 정리 (#257)
-- 분석 기준: 2026-03-19, room 테이블 179건
-- 처리 항목:
--   1. recommend_capacity_range = [50,50] (6건) → max_capacity 기준 역산
--   2. recommend_capacity_range 상한 > max_capacity (8건) → max_capacity 기준 clamp
--   3. recommend_capacity_range = [x,x] 단일값 중 sadang/dream_sadang (9건) → 수동 보정
--   4. extra_charge = 0 (5건) → NULL


-- ────────────────────────────────────────────────
-- 1. recommend_capacity_range = [50,50] 수정 (6건)
--    max_capacity 기준으로 [max*0.4, max*0.8] 수준으로 역산
--    (정수 절삭, min >= 1 보장)
-- ────────────────────────────────────────────────
UPDATE room
SET recommend_capacity_range = int4range(
    GREATEST(1, ROUND(max_capacity * 0.4)::int),
    GREATEST(2, ROUND(max_capacity * 0.8)::int),
    '[]'
)
WHERE lower(recommend_capacity_range) = 50
  AND upper(recommend_capacity_range) = 50
  AND max_capacity > 0
  AND max_capacity < 50;


-- ────────────────────────────────────────────────
-- 2. recommend_capacity_range 상한 > max_capacity 수정 (8건)
--    상한을 max_capacity로 clamp, 하한은 min(기존 하한, max_capacity)
-- ────────────────────────────────────────────────
UPDATE room
SET recommend_capacity_range = int4range(
    LEAST(lower(recommend_capacity_range), max_capacity),
    max_capacity,
    '[]'
)
WHERE recommend_capacity_range IS NOT NULL
  AND upper(recommend_capacity_range) > max_capacity
  AND max_capacity > 0
  -- [50,50] 케이스는 위에서 처리했으므로 제외
  AND NOT (lower(recommend_capacity_range) = 50 AND upper(recommend_capacity_range) = 50);


-- ────────────────────────────────────────────────
-- 3. sadang / dream_sadang 단일값 수동 보정 (9건)
--    business_id: sadang=해당값, dream_sadang=해당값
--    실제 business_id 확인 후 적용 필요 — 아래는 조회용 SELECT
-- ────────────────────────────────────────────────
-- 현황 확인용 (실행 전 조회):
-- SELECT business_id, name, max_capacity, base_capacity, recommend_capacity_range
-- FROM room
-- WHERE lower(recommend_capacity_range) = upper(recommend_capacity_range) - 1
--    OR lower(recommend_capacity_range) = upper(recommend_capacity_range)
-- ORDER BY business_id, name;

-- sadang / dream_sadang: base_capacity 기반 정책 → [base_capacity, max_capacity]
-- TODO: 아래 WHERE 조건의 business_id 값을 실제 값으로 교체 후 실행
-- UPDATE room
-- SET recommend_capacity_range = int4range(base_capacity, max_capacity, '[]')
-- WHERE business_id IN (/* sadang business_id */, /* dream_sadang business_id */)
--   AND base_capacity IS NOT NULL
--   AND lower(recommend_capacity_range) = upper(recommend_capacity_range) - 1;


-- ────────────────────────────────────────────────
-- 4. extra_charge = 0 → NULL (5건)
-- ────────────────────────────────────────────────
UPDATE room
SET extra_charge = NULL
WHERE extra_charge = 0;


-- 결과 검증용
-- SELECT
--     COUNT(*) FILTER (WHERE lower(recommend_capacity_range) = 50 AND upper(recommend_capacity_range) = 50) AS sentinel_50_50,
--     COUNT(*) FILTER (WHERE upper(recommend_capacity_range) > max_capacity) AS range_exceeds_max,
--     COUNT(*) FILTER (WHERE lower(recommend_capacity_range) = upper(recommend_capacity_range) - 1) AS single_value_range,
--     COUNT(*) FILTER (WHERE extra_charge = 0) AS extra_charge_zero
-- FROM room;
