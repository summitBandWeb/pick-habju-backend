import os
import json
import time
import tempfile
import logging
from prometheus_client import REGISTRY
import httpx
from app.core.config import DISCORD_WEBHOOK_URL, APP_ENV

logger = logging.getLogger(__name__)

SNAPSHOT_FILE = os.path.join(tempfile.gettempdir(), "daily_discord_report_snapshot.json")

async def _acquire_distributed_lock(lock_key: str, ttl_seconds: int = 60) -> bool:
    """
    다중 인스턴스 스케줄러 중복 실행 방지를 위한 분산 락 획득 (File-based fallback)
    (실제 프로덕션 환경에선 Redis SETNX 또는 DB Row Lock을 연동해야 합니다.)
    """
    lock_file = os.path.join(tempfile.gettempdir(), f"{lock_key}.lock")
    now = time.time()
    
    # Stale 락 클린업 시도
    try:
        if os.path.exists(lock_file):
            with open(lock_file, 'r') as f:
                data = json.load(f)
            if now > data.get('expires_at', 0):
                os.remove(lock_file)
    except Exception:
        pass

    try:
        fd = os.open(lock_file, os.O_CREAT | os.O_EXCL | os.O_RDWR)
        with os.fdopen(fd, 'w') as f:
            json.dump({'expires_at': now + ttl_seconds, 'pid': os.getpid()}, f)
        return True
    except FileExistsError:
        return False
    except Exception as e:
        logger.error(f"Lock acquisition error: {e}")
        return False

def _release_distributed_lock(lock_key: str):
    """
    락 소유권자(PID)가 일치하는 경우에만 락 해제
    """
    lock_file = os.path.join(tempfile.gettempdir(), f"{lock_key}.lock")
    try:
        if os.path.exists(lock_file):
            with open(lock_file, 'r') as f:
                data = json.load(f)
            if data.get('pid') == os.getpid():
                os.remove(lock_file)
    except Exception:
        pass

def _load_snapshot() -> dict:
    try:
        if os.path.exists(SNAPSHOT_FILE):
            with open(SNAPSHOT_FILE, 'r') as f:
                return json.load(f)
    except Exception:
        pass
    return {"total_requests": 0, "total_errors": 0, "total_duration": 0.0}

def _save_snapshot(data: dict):
    try:
        with open(SNAPSHOT_FILE, 'w') as f:
            json.dump(data, f)
    except Exception as e:
        logger.error(f"Failed to save metrics snapshot: {e}")

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
    if not await _acquire_distributed_lock(lock_key):
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
                    
        # 3. 누적 누수 방지를 위한 Delta 계산 (이전 스냅샷과의 차이)
        snapshot = _load_snapshot()
        total_requests = max(0, current_requests - snapshot.get("total_requests", 0))
        total_errors = max(0, current_errors - snapshot.get("total_errors", 0))
        total_duration = max(0.0, current_duration - snapshot.get("total_duration", 0.0))
        
        # 새로운 스냅샷 반영
        _save_snapshot({
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
        _release_distributed_lock(lock_key)
