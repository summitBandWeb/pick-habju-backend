-- -----------------------------------------------------
-- 2차 마이그레이션: Branch 테이블에 좌표 컬럼 추가
-- -----------------------------------------------------
-- 작성일: 2026-02-12
-- 설명: 네이버 지도 크롤링 결과를 저장하기 위해 위도(lat), 경도(lng) 컬럼을 추가합니다.

-- 1. 위도 (Latitude) 추가
ALTER TABLE branch 
ADD COLUMN lat NUMERIC(10, 7) NULL;

-- 2. 경도 (Longitude) 추가
ALTER TABLE branch 
ADD COLUMN lng NUMERIC(10, 7) NULL;

-- 3. 컬럼 코멘트 추가
COMMENT ON COLUMN branch.lat IS '위도 (Latitude)';
COMMENT ON COLUMN branch.lng IS '경도 (Longitude)';
