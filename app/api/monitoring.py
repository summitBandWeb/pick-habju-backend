import logging
from fastapi import APIRouter, HTTPException
from app.services.monitoring_service import send_discord_report

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/monitoring", tags=["Monitoring"])

@router.post("/daily-report", summary="Trigger Daily Discord Report")
async def trigger_daily_report():
    """
    GCP Cloud Scheduler 등 외부 인프라에서 매일 정해진 시간에 호출할 엔드포인트입니다.
    이 엔드포인트는 Prometheus 지표를 정리하여 Discord로 데일리 리포트를 전송합니다.
    """
    try:
        # Serverless(Cloud Run 등) 구동 환경에서는 응답 반환 후 CPU 할당이 제한되므로,
        # BackgroundTasks를 사용하지 않고 동기적으로 로직을 끝까지 수행해야 완전한 실행이 보장됩니다.
        # GCP Cloud Scheduler에서 실패를 즉각적으로 감지성(Visibility) 할 수 있도록 예외 시 500 에러를 반환합니다.
        await send_discord_report()
        return {"ok": True, "message": "Daily report triggered successfully"}
    except Exception as e:
        logger.error(f"Failed to trigger daily report: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error while triggering report")
