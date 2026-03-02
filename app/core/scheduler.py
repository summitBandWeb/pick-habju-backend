import logging
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from zoneinfo import ZoneInfo
from app.services.monitoring_service import send_discord_report

logger = logging.getLogger(__name__)

# 전역 스케줄러 인스턴스
scheduler = AsyncIOScheduler(timezone=ZoneInfo("Asia/Seoul"))

def start_scheduler():
    """
    애플리케이션 시작 시 APScheduler를 설정하고 구동합니다.
    매일 오전 9시(KST 등 로컬 타임존 기준)에 데일리 리포트 작업을 등록합니다.
    """
    if not scheduler.running:
        try:
            # 매일 아침 9시에 실행
            scheduler.add_job(
                send_discord_report,
                'cron',
                hour=9,
                minute=0,
                id='daily_discord_report',
                replace_existing=True
            )

            scheduler.start()
            logger.info("Scheduler started successfully: Daily report registered for 09:00.")
        except Exception as e:
            logger.error(f"Failed to start scheduler: {e}", exc_info=True)

def shutdown_scheduler():
    """
    애플리케이션 종료 시 APScheduler를 안전하게 종료합니다.
    """
    if scheduler.running:
        scheduler.shutdown(wait=False)
        logger.info("Scheduler shut down successfully.")
