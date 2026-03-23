-- Migration 158: capacity 필드 이상값 정리 (#257)
-- 분석 기준: 2026-03-19, room 테이블 179건
-- 처리 항목:
--   1. recommend_capacity_range = [50,50] (6건) → max_capacity 기준 역산
--   2. recommend_capacity_range 상한 > max_capacity (8건) → max_capacity 기준 clamp
--   3. recommend_capacity_range = [x,x] 단일값 중 sadang/dream_sadang → 158b로 분리
--   4. extra_charge = 0 (5건) → NULL
--
-- NOTE: recommend_capacity_range 컬럼 타입은 integer[] (배열)
--       int4range 함수 및 lower()/upper() 대신 배열 인덱스([1], [2]) 사용
--
-- sadang/dream_sadang 단일값 보정은 별도 파일로 분리:
--   → migrations/158b_fix_sadang_capacity.sql


-- ────────────────────────────────────────────────
-- [P1 사전 검증] UPDATE 1 실행 전 반드시 아래 SELECT를 먼저 실행하세요.
-- 0건이면 현재 조건(max_capacity < 50) 유지 가능.
-- 1건 이상이면 조건 범위 재검토 필요.
-- ────────────────────────────────────────────────
-- SELECT biz_item_id, name, max_capacity, recommend_capacity_range
-- FROM room
-- WHERE recommend_capacity_range[1] = 50
--   AND recommend_capacity_range[2] = 50
--   AND max_capacity >= 50;


BEGIN;

-- ────────────────────────────────────────────────
-- 1. recommend_capacity_range = [50,50] 수정 (6건)
--    max_capacity 기준으로 [max-1, max] 적용 (delta=1 정책과 동일)
--    하한 최솟값 1 보장
--    조건: max_capacity < 50 — [50,50]이 실제 범위인 케이스(max>=50) 보호
-- ────────────────────────────────────────────────
UPDATE room
SET recommend_capacity_range = ARRAY[
    GREATEST(1, max_capacity - 1),
    max_capacity
]
WHERE recommend_capacity_range[1] = 50
  AND recommend_capacity_range[2] = 50
  AND max_capacity > 0
  AND max_capacity < 50;


-- ────────────────────────────────────────────────
-- 2. recommend_capacity_range 상한 > max_capacity 수정 (8건)
--    상한을 max_capacity로 clamp, 하한은 min(기존 하한, max_capacity)
--    하한 최솟값 1 보장 (lo=0 방지)
-- ────────────────────────────────────────────────
UPDATE room
SET recommend_capacity_range = ARRAY[
    GREATEST(1, LEAST(recommend_capacity_range[1], max_capacity)),
    max_capacity
]
WHERE recommend_capacity_range IS NOT NULL
  AND recommend_capacity_range[2] > max_capacity
  AND max_capacity > 0
  -- [50,50] 케이스는 위에서 처리했으므로 제외
  AND NOT (recommend_capacity_range[1] = 50 AND recommend_capacity_range[2] = 50);


-- ────────────────────────────────────────────────
-- 3. extra_charge = 0 → NULL (5건)
-- ────────────────────────────────────────────────
UPDATE room
SET extra_charge = NULL
WHERE extra_charge = 0;


COMMIT;


-- 결과 검증용 (COMMIT 후 별도 실행)
-- SELECT
--     COUNT(*) FILTER (WHERE recommend_capacity_range[1] = 50 AND recommend_capacity_range[2] = 50) AS sentinel_50_50,
--     COUNT(*) FILTER (WHERE recommend_capacity_range IS NOT NULL AND recommend_capacity_range[2] > max_capacity) AS range_exceeds_max,
--     COUNT(*) FILTER (WHERE recommend_capacity_range IS NOT NULL AND recommend_capacity_range[1] < 1) AS range_lo_zero,
--     COUNT(*) FILTER (WHERE extra_charge = 0) AS extra_charge_zero
-- FROM room;
-- 기대값: 모든 컬럼 0
