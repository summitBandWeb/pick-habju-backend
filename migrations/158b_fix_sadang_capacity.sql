-- Migration 158b: sadang/dream_sadang recommend_capacity_range 단일값 보정
-- 관련 이슈: #257 (Sub-issue of #256)
-- 선행 조건: migrations/158_fix_capacity_data_quality.sql 실행 완료 후 적용
--
-- 대상: base_capacity 기반 정책 지점(sadang, dream_sadang)의 단일값 range
--   → [base_capacity, max_capacity] 로 보정
--
-- 실행 전 아래 SELECT로 business_id 및 대상 룸 확인 필수


-- ────────────────────────────────────────────────
-- 현황 확인용 SELECT (실행 후 business_id 확인)
-- ────────────────────────────────────────────────
-- SELECT business_id, name, max_capacity, base_capacity, recommend_capacity_range
-- FROM room
-- WHERE recommend_capacity_range[1] = recommend_capacity_range[2]
--   AND base_capacity IS NOT NULL
-- ORDER BY business_id, name;


-- ────────────────────────────────────────────────
-- UPDATE (business_id 확인 후 주석 해제하여 실행)
-- ────────────────────────────────────────────────
-- TODO: sadang, dream_sadang의 실제 business_id를 아래에 입력 후 실행

-- BEGIN;

-- UPDATE room
-- SET recommend_capacity_range = ARRAY[base_capacity, max_capacity]
-- WHERE business_id IN (/* sadang */, /* dream_sadang */)
--   AND base_capacity IS NOT NULL
--   AND base_capacity < max_capacity
--   AND recommend_capacity_range[1] = recommend_capacity_range[2];

-- COMMIT;


-- 결과 검증용
-- SELECT business_id, name, max_capacity, base_capacity, recommend_capacity_range
-- FROM room
-- WHERE business_id IN (/* sadang */, /* dream_sadang */)
-- ORDER BY business_id, name;
