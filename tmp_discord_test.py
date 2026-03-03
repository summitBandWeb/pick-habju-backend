import asyncio
import logging
from app.services.monitoring_service import send_discord_report
from app.core.config import DISCORD_WEBHOOK_URL

# 로깅 설정
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

async def main():
    if not DISCORD_WEBHOOK_URL:
        print("❌ DISCORD_WEBHOOK_URL이 설정되어 있지 않습니다.")
        print("개발 환경의 .env (혹은 시스템 환경변수)에 DISCORD_WEBHOOK_URL를 채워주세요.")
        return

    print(f"✅ Webhook URL 확인됨: {DISCORD_WEBHOOK_URL[:40]}...")
    print("🚀 디스코드 알림을 수동으로 전송합니다...")
    
    await send_discord_report()
    
    print("✅ 전송 시도가 완료되었습니다. 디스코드 채널을 확인해보세요!")

if __name__ == "__main__":
    asyncio.run(main())
