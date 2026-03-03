import os
import json
import time
import tempfile
import logging
from prometheus_client import REGISTRY
import httpx
from app.core.config import DISCORD_WEBHOOK_URL, APP_ENV

logger = logging.getLogger(__name__)

class SnapshotStore:
    async def acquire_lock(self, lock_key: str, ttl_seconds: int = 60) -> bool:
        raise NotImplementedError
    def release_lock(self, lock_key: str):
        raise NotImplementedError
    def load_snapshot(self) -> dict:
        raise NotImplementedError
    def save_snapshot(self, data: dict):
        raise NotImplementedError

class LocalSnapshotStore(SnapshotStore):
    """
    WARNING: Local file-based locking/snapshotting is not suitable for multi-server (e.g. AWS ECS across multiple nodes)
    or serverless environments without a shared EFS. This works fine for single-node deployments.
    """
    def __init__(self):
        self.snapshot_file = os.path.join(tempfile.gettempdir(), "daily_discord_report_snapshot.json")

    async def acquire_lock(self, lock_key: str, ttl_seconds: int = 60) -> bool:
        lock_file = os.path.join(tempfile.gettempdir(), f"{lock_key}.lock")
        now = time.time()
        
        try:
            if os.path.exists(lock_file):
                with open(lock_file, 'r') as f:
                    data = json.load(f)
                if now > data.get('expires_at', 0):
                    os.remove(lock_file)
        except Exception as e:
            logger.warning(f"Failed to clean stale lock {lock_file}: {e}", exc_info=True)

        try:
            fd = os.open(lock_file, os.O_CREAT | os.O_EXCL | os.O_RDWR)
            with os.fdopen(fd, 'w') as f:
                json.dump({'expires_at': now + ttl_seconds, 'pid': os.getpid()}, f)
            return True
        except FileExistsError:
            return False
        except Exception as e:
            logger.warning(f"Lock acquisition error: {e}", exc_info=True)
            return False

    def release_lock(self, lock_key: str):
        lock_file = os.path.join(tempfile.gettempdir(), f"{lock_key}.lock")
        try:
            if os.path.exists(lock_file):
                with open(lock_file, 'r') as f:
                    data = json.load(f)
                if data.get('pid') == os.getpid():
                    os.remove(lock_file)
        except Exception as e:
            logger.warning(f"Failed to release lock {lock_file}: {e}", exc_info=True)

    def load_snapshot(self) -> dict:
        try:
            if os.path.exists(self.snapshot_file):
                with open(self.snapshot_file, 'r') as f:
                    return json.load(f)
        except Exception as e:
            logger.warning(f"Failed to load snapshot {self.snapshot_file}: {e}", exc_info=True)
        return {"total_requests": 0, "total_errors": 0, "total_duration": 0.0}

    def save_snapshot(self, data: dict):
        try:
            with open(self.snapshot_file, 'w') as f:
                json.dump(data, f)
        except Exception as e:
            logger.warning(f"Failed to save metrics snapshot: {e}", exc_info=True)

# TODO: Replace with remote store (e.g. RedisSnapshotStore) when multi-node scaling is configured
snapshot_store: SnapshotStore = LocalSnapshotStore()


async def send_discord_report():
    """
    Prometheus in-memory REGISTRY를 분석하여 지난 24시간 리포트(이전 실행 스냅샷과의 Delta)
    통계를 계산하고, Discord 웹훅으로 전송합니다.
    """
    if not DISCORD_WEBHOOK_URL:
        logger.warning("Discord webhook URL is not set. Skipping daily report.")
        return
        
    lock_key = "daily_discord_report_lock"
    # 다중 인스턴스 중복 실행 방지 (분산 락 획득)
    if not await snapshot_store.acquire_lock(lock_key):
        logger.info("Another instance is running the daily report. Skipping...")
        return

    try:
        # 1. 지표 초기화 (수집)
        current_requests = 0
        current_errors = 0   # 500대 에러
        current_duration = 0.0

        # 2. Prometheus REGISTRY 분석
        for metric in REGISTRY.collect():
            for sample in metric.samples:
                # 헬스체크 엔드포인트에 대한 요청만 필터링
                if sample.labels.get('path') not in ('/health', '/ping'):
                    continue
                    
                if sample.name == "http_requests_total":
                    # sample.labels['status_code']로 접근
                    current_requests += sample.value
                    if str(sample.labels.get('status_code', '')).startswith('5'):
                        current_errors += sample.value
                elif sample.name == "http_request_duration_seconds_sum":
                    # Histogram의 sum을 통해 총 지연 시간 획득
                    current_duration += sample.value
                    
        # 3. 누적 누수 방지를 위한 Delta 계산 및 카운터 재시작 대처
        snapshot = snapshot_store.load_snapshot()
        snap_reqs = snapshot.get("total_requests", 0)
        snap_errs = snapshot.get("total_errors", 0)
        snap_dur = snapshot.get("total_duration", 0.0)
        
        # 만약 current가 snapshot보다 작다면 Prometheus 프로세스가 재시작되어 카운터가 리셋된 것
        total_requests = current_requests if current_requests < snap_reqs else current_requests - snap_reqs
        total_errors = current_errors if current_errors < snap_errs else current_errors - snap_errs
        total_duration = current_duration if current_duration < snap_dur else current_duration - snap_dur
        
        # 새로운 스냅샷 반영
        snapshot_store.save_snapshot({
            "total_requests": current_requests,
            "total_errors": current_errors,
            "total_duration": current_duration
        })
        
        # 4. 통계 산출
        avg_latency = (total_duration / total_requests) if total_requests > 0 else 0
        uptime_percent = ((total_requests - total_errors) / total_requests * 100) if total_requests > 0 else 100.0
        
        # 5. 디스코드 메시지 포맷팅
        env_label = APP_ENV.upper()
        message = {
            "content": None,
            "embeds": [
                {
                    "title": f"📊 픽합주 데일리 헬스체크 리포트 [{env_label}]",
                    "description": "최근 24시간 수집된 모니터링 메트릭 요약 결과입니다.",
                    "color": 65280 if uptime_percent >= 99.0 else 16711680,
                    "fields": [
                        {
                            "name": "성공/총 요청 수",
                            "value": f"{int(total_requests - total_errors)} / {int(total_requests)}",
                            "inline": True
                        },
                        {
                            "name": "50x 에러 발생 횟수",
                            "value": f"{int(total_errors)}회",
                            "inline": True
                        },
                        {
                            "name": "요청 성공률 (Success Rate)",
                            "value": f"{uptime_percent:.2f}%",
                            "inline": True
                        },
                        {
                            "name": "평균 응답 지연 (Latency)",
                            "value": f"{avg_latency:.3f}초",
                            "inline": True
                        }
                    ],
                    "footer": {
                        "text": "Generated by Monitoring Service"
                    }
                }
            ]
        }
        
        # 6. 웹훅 발송 (타임아웃은 길게 설정하지 않음)
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.post(DISCORD_WEBHOOK_URL, json=message)
            resp.raise_for_status()
            logger.info("Successfully sent daily report to Discord.")
            
    except Exception as e:
        logger.error(f"Failed to generate or send daily report: {e}", exc_info=True)
    finally:
        snapshot_store.release_lock(lock_key)
