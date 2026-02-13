-- Migration v2.0.0: Metadata Algorithm Update
-- Description: Add columns for dynamic pricing, range capacity, and branch policies.

-- 1. Branch 테이블 변경
ALTER TABLE "public"."branch"
ADD COLUMN IF NOT EXISTS "standby_days" integer DEFAULT 0,
ADD COLUMN IF NOT EXISTS "phone_number" text,
ADD COLUMN IF NOT EXISTS "display_name" text;

COMMENT ON COLUMN "public"."branch"."standby_days" IS '오픈 대기 일수 (오늘 + N일부터 예약 가능)';
COMMENT ON COLUMN "public"."branch"."phone_number" IS '지점 대표 전화번호';
COMMENT ON COLUMN "public"."branch"."display_name" IS '지점 노출용 이름';

-- 2. Room 테이블 변경 (Parallel Change 적용)
-- 기존 recommend_capacity는 건드리지 않고 새로운 범위 컬럼 추가
ALTER TABLE "public"."room"
ADD COLUMN IF NOT EXISTS "recommend_capacity_range" integer[],
ADD COLUMN IF NOT EXISTS "price_config" jsonb DEFAULT '[]'::jsonb;

COMMENT ON COLUMN "public"."room"."recommend_capacity_range" IS '권장 인원 범위 [min, max]';
COMMENT ON COLUMN "public"."room"."price_config" IS '동적 가격 및 예약 정책 설정 (JSONB)';

-- 3. 데이터 보정 (Backfill)
-- 기존 recommend_capacity 값을 이용하여 범위 초기화 [n, n]
UPDATE "public"."room"
SET "recommend_capacity_range" = ARRAY[recommend_capacity, recommend_capacity]
WHERE "recommend_capacity_range" IS NULL;
