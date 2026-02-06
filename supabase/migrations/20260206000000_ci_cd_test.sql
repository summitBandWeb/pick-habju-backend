-- =============================================================================
-- 테스트용 마이그레이션 파일
-- =============================================================================
-- 목적: CI/CD 파이프라인의 백업 및 마이그레이션 기능 테스트
-- 테스트 완료 후 이 파일은 삭제하거나 유지해도 무방합니다.
-- =============================================================================

-- 테스트 테이블 생성 (이미 존재하면 무시)
CREATE TABLE IF NOT EXISTS _ci_cd_test (
    id SERIAL PRIMARY KEY,
    test_name TEXT NOT NULL DEFAULT 'ci_cd_migration_test',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    metadata JSONB DEFAULT '{}'::jsonb
);

-- 테스트 레코드 삽입
INSERT INTO _ci_cd_test (test_name, metadata)
VALUES (
    'pipeline_test_' || to_char(NOW(), 'YYYYMMDD_HH24MISS'),
    jsonb_build_object(
        'workflow', 'deploy-test.yaml',
        'environment', 'test',
        'timestamp', NOW()
    )
);

-- 확인용 메시지
DO $$
BEGIN
    RAISE NOTICE '✅ CI/CD Migration Test Completed Successfully';
END $$;
