-- Migration 159: 요일 variant 병합 후 고아 행(orphan row) 정리 (#259)
--
-- 배경:
--   _merge_day_variant_rooms 로직이 배포된 후 재크롤링 시 주말 variant 룸(we_id)은
--   파이프라인에서 드롭되어 DB 업데이트를 받지 못하고 고아 행으로 잔존함.
--   이 마이그레이션은 "평일/주말 쌍으로 존재하는 룸 중 주말 룸"을 정리한다.
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
-- 동일 business_id 내에서 base_name이 동일한 weekday/weekend 쌍을 찾아 weekend를 대상으로 조회
-- ────────────────────────────────────────────────
SELECT
    we.biz_item_id   AS orphan_biz_item_id,
    we.name          AS orphan_name,
    wd.biz_item_id   AS primary_biz_item_id,
    wd.name          AS primary_name,
    we.business_id
FROM room we
JOIN room wd
  ON wd.business_id = we.business_id
 AND regexp_replace(wd.name, '\s*\((?:평일\s*낮|평일\s*오전|평일\s*야간|평일)\)\s*$', '')
   = regexp_replace(we.name, '\s*\((?:주말[^)]*|공휴일)\)\s*$', '')
 AND wd.biz_item_id <> we.biz_item_id
WHERE we.name ~ '\((?:주말|주말/공휴일|공휴일)'
  AND wd.name ~ '\((?:평일'
ORDER BY we.business_id, we.name;


-- ────────────────────────────────────────────────
-- Step 1: 고아 주말 variant 룸 삭제
-- Step 0 결과를 확인한 뒤 실행하세요.
-- ────────────────────────────────────────────────
BEGIN;

DELETE FROM room
WHERE biz_item_id IN (
    SELECT we.biz_item_id
    FROM room we
    JOIN room wd
      ON wd.business_id = we.business_id
     AND regexp_replace(wd.name, '\s*\((?:평일\s*낮|평일\s*오전|평일\s*야간|평일)\)\s*$', '')
       = regexp_replace(we.name, '\s*\((?:주말[^)]*|공휴일)\)\s*$', '')
     AND wd.biz_item_id <> we.biz_item_id
    WHERE we.name ~ '\((?:주말|주말/공휴일|공휴일)'
      AND wd.name ~ '\((?:평일'
);

-- 삭제 건수 확인
SELECT 'deleted orphan variant rooms' AS action, COUNT(*) AS remaining_weekend_variants
FROM room
WHERE name ~ '\((?:주말|주말/공휴일|공휴일)';

COMMIT;
