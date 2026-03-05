-- migration: 156_monitoring_shared_lock.sql
-- Description: Table for shared locking and metrics snapshot storage across multiple instances.

CREATE TABLE IF NOT EXISTS monitoring_metadata (
    key TEXT PRIMARY KEY,
    data JSONB DEFAULT '{}'::jsonb,
    expires_at TIMESTAMPTZ,
    owner_pid INTEGER,
    updated_at TIMESTAMPTZ DEFAULT now()
);

COMMENT ON TABLE monitoring_metadata IS '모니터링 서비스 관리를 위한 메타데이터 및 공유 락 테이블';
COMMENT ON COLUMN monitoring_metadata.key IS '데이터 식별 키 (예: daily_discord_report_lock)';
COMMENT ON COLUMN monitoring_metadata.data IS '스냅샷 등 JSON 데이터';
COMMENT ON COLUMN monitoring_metadata.expires_at IS '락 만료 시간';
COMMENT ON COLUMN monitoring_metadata.owner_pid IS '락을 소유한 인스턴스의 프로세스 ID';
