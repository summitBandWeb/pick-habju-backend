-- Migration 160: recommend_capacity 컬럼 및 CHECK 제약 드롭 (#268)
--
-- 배경:
--   PR #272에서 recommend_capacity 단일값 파이프라인을 전면 제거하고
--   recommend_capacity_range (배열)로 대체 완료. 컬럼에는 min(max_cap, FLAG)
--   더미값만 저장되고 있어 실질적 의미 없음.
--
-- 삭제 대상:
--   1. CHECK 제약: chk_room_cap_logic (max_capacity >= recommend_capacity)
--   2. 컬럼: room.recommend_capacity
--
-- 전제 조건:
--   - PR #272 배포 완료 (코드에서 recommend_capacity 키 제거된 상태)
--   - 프론트엔드 recommend_capacity 미참조 확인 완료


-- ────────────────────────────────────────────────
-- [사전 검증] 현재 recommend_capacity 분포 확인
-- 마이그레이션 실행 전 반드시 아래 SELECT를 먼저 실행하세요.
-- ────────────────────────────────────────────────
-- SELECT
--     COUNT(*) AS total_rooms,
--     COUNT(*) FILTER (WHERE recommend_capacity = max_capacity) AS dummy_min_clamp,
--     COUNT(*) FILTER (WHERE recommend_capacity = 100) AS flag_100,
--     COUNT(*) FILTER (WHERE recommend_capacity NOT IN (max_capacity, 100) AND recommend_capacity > 1) AS legacy_heuristic,
--     COUNT(*) FILTER (WHERE recommend_capacity = 1) AS default_1
-- FROM room;
-- 기대값: legacy_heuristic = 0 (PR #272 배포 후 재크롤링 완료 시)


BEGIN;

-- 1. CHECK 제약 제거 (컬럼 드롭 전에 먼저)
ALTER TABLE room DROP CONSTRAINT IF EXISTS chk_room_cap_logic;

-- 2. recommend_capacity 컬럼 드롭
ALTER TABLE room DROP COLUMN IF EXISTS recommend_capacity;

COMMIT;


-- ────────────────────────────────────────────────
-- [사후 검증] COMMIT 후 별도 실행
-- ────────────────────────────────────────────────
-- SELECT column_name
-- FROM information_schema.columns
-- WHERE table_name = 'room' AND column_name = 'recommend_capacity';
-- 기대값: 0건 (컬럼 삭제 확인)
--
-- SELECT conname
-- FROM pg_constraint
-- WHERE conrelid = 'room'::regclass AND conname = 'chk_room_cap_logic';
-- 기대값: 0건 (제약조건 삭제 확인)
