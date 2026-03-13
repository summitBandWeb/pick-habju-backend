-- branch 테이블의 lat, lng 기반 지리적 검색 최적화를 위한 복합 인덱스 추가
CREATE INDEX IF NOT EXISTS idx_branch_lat_lng ON public.branch (lat, lng);
