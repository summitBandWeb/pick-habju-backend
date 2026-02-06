-- -----------------------------------------------------
-- 1. 지점 (Branch) 테이블
-- -----------------------------------------------------
CREATE TABLE branch (
    business_id VARCHAR(50) NOT NULL, -- 지점 ID
    name        VARCHAR(100) NOT NULL, -- 지점 이름 (ex: 비쥬합주실 1호점)
    
    CONSTRAINT pk_branch PRIMARY KEY (business_id)
);

-- 테이블 및 컬럼 코멘트 (PostgreSQL 방식)
COMMENT ON TABLE branch IS '합주실 지점 정보';
COMMENT ON COLUMN branch.business_id IS '지점 고유 ID';
COMMENT ON COLUMN branch.name IS '지점 명칭';


-- -----------------------------------------------------
-- 2. 합주실 (Room) 테이블
-- -----------------------------------------------------
CREATE TABLE room (
    biz_item_id VARCHAR(50) NOT NULL, -- 합주실 룸 ID
    business_id VARCHAR(50) NOT NULL, -- 소속 지점 ID (FK)
    name        VARCHAR(100) NOT NULL, -- 룸 이름 (ex: 블랙룸)
    
    -- 인원 정보
    max_capacity       INTEGER NOT NULL DEFAULT 1, -- 최대 인원
    recommend_capacity INTEGER NOT NULL DEFAULT 1, -- 권장 인원
    
    -- 추가 요금 정보 (필수여부 X -> NULL 허용)
    base_capacity      INTEGER NULL,     -- 기본 인원 (초과 시 과금 기준)
    extra_charge       NUMERIC(15, 2) NULL,     -- 초과 인원/시간당 추가 요금
    
    -- 가격 및 예약 규칙
    price_per_hour     NUMERIC(15, 2) NOT NULL DEFAULT 0, -- 시간당 기본 요금
    can_reserve_one_hour    BOOLEAN NOT NULL DEFAULT TRUE, -- 1시간 예약 가능 여부
    requires_call_on_sameday BOOLEAN NOT NULL DEFAULT FALSE, -- 당일 예약 시 전화 필수 여부
    
    CONSTRAINT pk_room PRIMARY KEY (business_id, biz_item_id),
    
    -- FK: 지점 삭제 시 룸 정보 보호를 위해 RESTRICT 설정 (정책에 따라 CASCADE 변경 가능)
    CONSTRAINT fk_room_branch
        FOREIGN KEY (business_id) REFERENCES branch (business_id)
        ON DELETE CASCADE ON UPDATE CASCADE,
  
    -- [CHECK Constraints: 데이터 무결성 보장]
    -- 1. 가격은 0원 이상이어야 함
    CONSTRAINT chk_room_price_positive CHECK (price_per_hour >= 0),
    -- 2. 최대 인원은 1명 이상이어야 함
    CONSTRAINT chk_room_max_cap_min CHECK (max_capacity >= 1),
    -- 3. 최대 인원은 권장 인원보다 크거나 같아야 논리적임
    CONSTRAINT chk_room_cap_logic CHECK (max_capacity >= recommend_capacity)
);

-- 테이블 및 컬럼 코멘트
COMMENT ON TABLE room IS '합주실 개별 룸 정보';
COMMENT ON COLUMN room.max_capacity IS '최대 수용 인원';
COMMENT ON COLUMN room.base_capacity IS '추가 요금 기준이 되는 기본 인원 (NULL 가능)';
COMMENT ON COLUMN room.requires_call_on_sameday IS '당일 예약 시 전화 문의 필수 여부';


-- -----------------------------------------------------
-- 3. 룸 이미지 (RoomImage) 테이블
-- -----------------------------------------------------
CREATE TABLE room_image (
    image_id    BIGSERIAL NOT NULL,
    
    -- 부모(Room)를 찾으려면 두 개의 ID가 모두 필요함
    business_id VARCHAR(50) NOT NULL,
    biz_item_id VARCHAR(50) NOT NULL,
    
    image_url   TEXT NOT NULL,
    sort_order  INTEGER DEFAULT 0,
    
    CONSTRAINT pk_room_image PRIMARY KEY (image_id),
    
    -- 외래키도 2개 컬럼을 묶어서 설정해야 함
    CONSTRAINT fk_image_room
        FOREIGN KEY (business_id, biz_item_id) 
        REFERENCES room (business_id, biz_item_id)
        ON DELETE CASCADE ON UPDATE CASCADE
);

-- 테이블 및 컬럼 코멘트
COMMENT ON TABLE room_image IS '합주실 룸 상세 이미지 리스트';
COMMENT ON COLUMN room_image.image_url IS 'S3 등 스토리지에 저장된 이미지 경로';

-- -----------------------------------------------------
-- 4. 인덱스 설정 (성능 최적화)
-- -----------------------------------------------------
-- 특정 지점의 모든 방을 조회할 때 성능 향상
CREATE INDEX idx_image_room_composite ON room_image(business_id, biz_item_id);
