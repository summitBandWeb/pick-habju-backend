-- metadata v2 migration (idempotent)
-- Issue: #155

BEGIN;

-- 1) Schema updates
ALTER TABLE room
    ADD COLUMN IF NOT EXISTS recommend_capacity_range int4range,
    ADD COLUMN IF NOT EXISTS base_capacity integer DEFAULT NULL,
    ADD COLUMN IF NOT EXISTS extra_charge integer DEFAULT NULL,
    ADD COLUMN IF NOT EXISTS price_config jsonb DEFAULT NULL;

COMMENT ON COLUMN room.recommend_capacity_range IS '권장 인원 범위 [min, max]';
COMMENT ON COLUMN room.base_capacity IS '추가 요금 발생 기준 인원';
COMMENT ON COLUMN room.extra_charge IS '1인당 시간당 추가 요금';
COMMENT ON COLUMN room.price_config IS '요일/시간대별 동적 가격 설정(JSON)';

-- 2) Backfill: legacy recommend_capacity -> recommend_capacity_range
UPDATE room
SET recommend_capacity_range = int4range(
    GREATEST(1, recommend_capacity - 2),
    recommend_capacity,
    '[]'
)
WHERE recommend_capacity IS NOT NULL
  AND recommend_capacity >= 1
  AND recommend_capacity_range IS NULL;

-- 3) Backfill: legacy price_per_hour -> price_config
UPDATE room
SET price_config = jsonb_build_object(
    'default', price_per_hour,
    'overrides', '[]'::jsonb,
    'surcharges', '[]'::jsonb
)
WHERE price_per_hour IS NOT NULL
  AND price_config IS NULL;

COMMIT;

-- 4) Verification queries
-- SELECT COUNT(*) AS null_capacity_range FROM room WHERE recommend_capacity IS NOT NULL AND recommend_capacity_range IS NULL;
-- SELECT COUNT(*) AS null_price_config FROM room WHERE price_per_hour IS NOT NULL AND price_config IS NULL;
-- SELECT biz_item_id, recommend_capacity, recommend_capacity_range FROM room WHERE recommend_capacity_range IS NULL LIMIT 20;
-- SELECT biz_item_id, price_per_hour, price_config FROM room WHERE price_config IS NULL LIMIT 20;
