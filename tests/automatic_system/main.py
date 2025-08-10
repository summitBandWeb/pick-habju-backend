# main.py

import logging
from discord_notifier import DiscordNotifier
from performance_tester import RoomAvailabilityPerformanceTester
from scheduler import PerformanceTestScheduler
import asyncio

# 애플리케이션 전역 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

def main():
    """메인 실행 함수"""
    try:
        # 설정 변수
        DISCORD_WEBHOOK_URL = "YOUR_DISCORD_WEBHOOK_URL_HERE"  # 🚨 실제 웹훅 URL로 변경하세요!

        # 객체 생성 및 의존성 주입
        notifier = DiscordNotifier(DISCORD_WEBHOOK_URL)
        tester = RoomAvailabilityPerformanceTester(notifier)
        scheduler = PerformanceTestScheduler(tester)

        print("실행 방식을 선택하세요:")
        print("1. 한 번만 실행")
        print("2. 주기적 자동 실행 (30분 간격)")
        print("3. 사용자 정의 간격으로 주기적 실행")

        choice = input("선택 (1-3): ").strip()

        if choice == "1":
            print("테스트를 한 번 실행합니다...")
            asyncio.run(tester.run_all_tests_and_notify())
            print("테스트 완료!")
        elif choice == "2":
            scheduler.start(interval_minutes=30)
        elif choice == "3":
            try:
                interval = int(input("실행 간격을 분 단위로 입력하세요: "))
                if interval <= 0:
                    print("간격은 1분 이상이어야 합니다.")
                else:
                    scheduler.start(interval_minutes=interval)
            except ValueError:
                print("오류: 유효한 숫자를 입력하세요.")
        else:
            print("잘못된 선택입니다. 프로그램을 종료합니다.")

    except ValueError as e:
        # DiscordNotifier에서 웹훅 URL이 유효하지 않을 때 발생
        logging.error(f"설정 오류: {e}")
    except Exception as e:
        logging.error(f"프로그램 실행 중 예상치 못한 오류 발생: {e}", exc_info=True)


if __name__ == "__main__":
    # 참고: 실제 크롤러 함수(get_dream_availability 등)와 의존성(RoomKey 등)이
    #       올바른 경로에 위치해야 정상적으로 동작합니다.
    #       예시 코드에서는 일부를 Mock 데이터로 대체했으니 실제 환경에 맞게 수정해주세요.
    main()