# main.py

import logging
from discord_notifier import DiscordNotifier
from performance_tester import RoomAvailabilityPerformanceTester
from scheduler import PerformanceTestScheduler

# 애플리케이션 전역 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

def main():
    """메인 실행 함수"""
    try:
        # --- 설정 변수 ---
        DISCORD_WEBHOOK_URL = "YOUR_DISCORD_WEBHOOK_URL_HERE"  # 🚨 실제 웹훅 URL로 변경하세요!

        # --- 객체 생성 및 의존성 주입 ---
        notifier = DiscordNotifier(DISCORD_WEBHOOK_URL)
        tester = RoomAvailabilityPerformanceTester(notifier)
        scheduler = PerformanceTestScheduler(tester)

        print("✅ 프로그램 시작. 매시간 간격으로 성능 테스트를 실행합니다.")
        scheduler.start(interval_minutes=60)


    except ValueError as e:
        # DiscordNotifier에서 웹훅 URL이 유효하지 않을 때 발생
        logging.error(f"설정 오류: {e}")
    except Exception as e:
        logging.error(f"프로그램 실행 중 예상치 못한 오류 발생: {e}", exc_info=True)


if __name__ == "__main__":
    main()