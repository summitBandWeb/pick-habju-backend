# scheduler.py

import asyncio
import schedule
import time
import logging
from performance_tester import RoomAvailabilityPerformanceTester

logger = logging.getLogger(__name__)

class PerformanceTestScheduler:
    """성능 테스트 스케줄러"""

    def __init__(self, tester: RoomAvailabilityPerformanceTester):
        self.tester = tester

    def _run_test_job(self):
        """스케줄러에서 실행할 작업 (비동기 함수를 동기적으로 실행)"""
        logger.info("🚀 스케줄된 테스트 작업을 시작합니다...")
        try:
            asyncio.run(self.tester.run_all_tests_and_notify())
        except Exception as e:
            logger.error(f"스케줄된 테스트 실행 중 심각한 오류 발생: {e}", exc_info=True)

    def start_hourly(self, run_immediately: bool = True): # [수정] 메서드 이름 및 매개변수 변경
        """
        매시간 간격으로 스케줄러를 시작합니다.

        :param run_immediately: 시작 즉시 첫 테스트를 실행할지 여부
        """
        logger.info("⏰ 매시간 간격으로 테스트 스케줄러를 시작합니다.") # [수정] 로그 메시지 변경
        logger.info("   (Ctrl+C를 눌러 종료할 수 있습니다)")

        if run_immediately:
            logger.info(">> 첫 번째 테스트를 즉시 실행합니다...")
            self._run_test_job()

        # [수정] 매 분(minutes) 대신 매 시(hour)를 사용하도록 변경
        schedule.every().hour.do(self._run_test_job)

        try:
            while True:
                schedule.run_pending()
                time.sleep(60)  # 1분마다 대기 중인 작업을 확인
        except KeyboardInterrupt:
            logger.info("\n🛑 테스트 스케줄러를 종료합니다.")