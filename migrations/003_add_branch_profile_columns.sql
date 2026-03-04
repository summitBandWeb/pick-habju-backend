-- -----------------------------------------------------
-- 3. branch 확장 컬럼 추가 (롤링 배포 호환)
-- -----------------------------------------------------
ALTER TABLE branch
    ADD COLUMN IF NOT EXISTS display_name VARCHAR(100),
    ADD COLUMN IF NOT EXISTS phone_number VARCHAR(30),
    ADD COLUMN IF NOT EXISTS standby_days INTEGER;

-- 기존 데이터는 표시명(display_name)이 비어 있으면 name으로 보정
UPDATE branch
SET display_name = name
WHERE display_name IS NULL;

COMMENT ON COLUMN branch.display_name IS '사용자 노출용 지점명';
COMMENT ON COLUMN branch.phone_number IS '지점 대표 전화번호';
COMMENT ON COLUMN branch.standby_days IS '예약 오픈까지 남은 일수';
