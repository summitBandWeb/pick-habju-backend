-- Migration 159: 요일 variant 병합 후 고아 행(orphan row) 정리 (#259)
--
-- 배경:
--   _merge_day_variant_rooms 로직이 배포된 후 재크롤링 시 주말 variant 룸(we_id)은
--   파이프라인에서 드롭되어 DB 업데이트를 받지 못하고 고아 행으로 잔존함.
--   이 마이그레이션은 "평일/주말 쌍으로 존재하는 룸 중 주말 룸"을 정리한다.
--
-- 병합 조건: Python _merge_day_variant_rooms와 동일
--   동일 business_id + base_name 그룹 내 weekday 1개 + weekend 1개, 나머지 0개
--   → 조건 불충족 그룹(variant 3개 이상 등)은 삭제하지 않음
--
-- 실행 시점:
--   1. _merge_day_variant_rooms 코드 배포 완료 후
--   2. 대상 business_id에 대해 재크롤링 완료 후
--      (재크롤링 시 _delete_variant_orphans가 자동으로 삭제하므로 이 스크립트는 보조 수단)
--   3. 재크롤링 전 수동 정리가 필요한 경우 이 스크립트를 사용
--
-- NOTE: room.name 컬럼에는 parsed clean_name이 저장됨
--       suffix 형식: "1번룸 (평일 낮)", "1번룸 (주말)" 등
--       (room_collection_service.py L1118: parsed.get("clean_name") or room["name"])
--
-- 실행 순서: Step 0(검증) → Step 1(삭제)
-- Step 0은 SELECT 전용 — 결과 확인 후 Step 1 진행


-- ────────────────────────────────────────────────
-- Step 0: 삭제 대상 사전 확인 (실행 후 결과 검토 필수)
-- 병합 조건(wd=1, we=1, other=0)을 충족하는 그룹의 weekend 룸만 조회
-- ────────────────────────────────────────────────
WITH base_names AS (
    -- 각 룸의 base_name과 day_class 계산 (Python _classify_day_variant 대응)
    SELECT
        biz_item_id,
        business_id,
        name,
        regexp_replace(
            name,
            '\s*\((?:평일\s*낮|평일\s*오전|평일\s*야간|주말/공휴일|주말|공휴일|평일|심야|야간|주간)\)\s*$',
            ''
        ) AS base_name,
        CASE
            WHEN name ~ '\((?:평일\s*낮|평일\s*오전|평일\s*야간|평일)\)$' THEN 'weekday'
            WHEN name ~ '\((?:주말/공휴일|주말|공휴일)\)$'                THEN 'weekend'
            ELSE 'other'
        END AS day_class
    FROM room
),
counts AS (
    -- base_name별 weekday/weekend/other 개수 집계
    SELECT
        business_id,
        base_name,
        COUNT(*) FILTER (WHERE day_class = 'weekday') AS wd_cnt,
        COUNT(*) FILTER (WHERE day_class = 'weekend') AS we_cnt,
        COUNT(*) FILTER (WHERE day_class = 'other')   AS other_cnt
    FROM base_names
    GROUP BY business_id, base_name
)
SELECT
    bn.biz_item_id AS orphan_biz_item_id,
    bn.name        AS orphan_name,
    bn.business_id,
    c.wd_cnt,
    c.we_cnt
FROM base_names bn
JOIN counts c
  ON c.business_id = bn.business_id
 AND c.base_name   = bn.base_name
WHERE bn.day_class = 'weekend'
  AND c.wd_cnt     = 1
  AND c.we_cnt     = 1
  AND c.other_cnt  = 0
ORDER BY bn.business_id, bn.name;


-- ────────────────────────────────────────────────
-- Step 1: 고아 주말 variant 룸 삭제
-- Step 0 결과를 확인한 뒤 실행하세요.
-- RETURNING으로 실제 삭제 건수를 보고합니다.
-- ────────────────────────────────────────────────
BEGIN;

WITH base_names AS (
    SELECT
        biz_item_id,
        business_id,
        regexp_replace(
            name,
            '\s*\((?:평일\s*낮|평일\s*오전|평일\s*야간|주말/공휴일|주말|공휴일|평일|심야|야간|주간)\)\s*$',
            ''
        ) AS base_name,
        CASE
            WHEN name ~ '\((?:평일\s*낮|평일\s*오전|평일\s*야간|평일)\)$' THEN 'weekday'
            WHEN name ~ '\((?:주말/공휴일|주말|공휴일)\)$'                THEN 'weekend'
            ELSE 'other'
        END AS day_class
    FROM room
),
counts AS (
    SELECT
        business_id,
        base_name,
        COUNT(*) FILTER (WHERE day_class = 'weekday') AS wd_cnt,
        COUNT(*) FILTER (WHERE day_class = 'weekend') AS we_cnt,
        COUNT(*) FILTER (WHERE day_class = 'other')   AS other_cnt
    FROM base_names
    GROUP BY business_id, base_name
),
orphans AS (
    -- 병합 조건 충족(wd=1, we=1, other=0)인 그룹의 weekend 룸만 삭제 대상
    SELECT bn.biz_item_id
    FROM base_names bn
    JOIN counts c
      ON c.business_id = bn.business_id
     AND c.base_name   = bn.base_name
    WHERE bn.day_class  = 'weekend'
      AND c.wd_cnt      = 1
      AND c.we_cnt      = 1
      AND c.other_cnt   = 0
),
deleted AS (
    DELETE FROM room
    WHERE biz_item_id IN (SELECT biz_item_id FROM orphans)
    RETURNING biz_item_id
)
SELECT 'deleted orphan variant rooms' AS action, COUNT(*) AS deleted_count
FROM deleted;

COMMIT;
