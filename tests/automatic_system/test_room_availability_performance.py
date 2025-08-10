import asyncio
import time
import requests
import traceback
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
from dataclasses import dataclass
import logging

# 로깅 설정
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 필요한 모듈들 (기존 프로젝트에서 import)
from app.models.dto import RoomKey, RoomAvailability
from app.crawler.dream_checker import get_dream_availability
from app.crawler.groove_checker import get_groove_availability
from app.crawler.naver_checker import get_naver_availability
from app.exception.groove_exception import GrooveLoginError, GrooveCredentialError
from app.utils.room_loader import load_rooms

@dataclass
class TestConfig:
    """테스트 설정을 담는 데이터클래스"""
    name: str
    rooms: List[RoomKey]
    hour_slots: List[str]
    checker_function: callable
    expected_count: Optional[int] = None

@dataclass
class TestResult:
    """테스트 결과를 담는 데이터클래스"""
    test_name: str
    execution_time: float
    error: Optional[str]
    result_count: int
    success: bool

    @property
    def status_emoji(self) -> str:
        return "✅" if self.success else "❌"

class RoomAvailabilityPerformanceTester:
    """합주실 가용성 성능 테스터"""

    def __init__(self, discord_webhook_url: str):
        self.discord_webhook_url = discord_webhook_url
        self.test_configs = self._initialize_test_configs()

    def _initialize_test_configs(self) -> List[TestConfig]:
        """테스트 설정 초기화 - 중복 제거 및 설정 중앙화"""
        tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")

        # 드림합주실 설정
        dream_rooms = [
            RoomKey(name="D룸", branch="드림합주실 사당점", business_id="dream_sadang", biz_item_id="29"),
            RoomKey(name="C룸", branch="드림합주실 사당점", business_id="dream_sadang", biz_item_id="28"),
            RoomKey(name="Q룸", branch="드림합주실 사당점", business_id="dream_sadang", biz_item_id="27"),
            RoomKey(name="S룸", branch="드림합주실 사당점", business_id="dream_sadang", biz_item_id="26"),
            RoomKey(name="V룸", branch="드림합주실 사당점", business_id="dream_sadang", biz_item_id="25"),
        ]

        # 그루브합주실 설정 (동적 로딩)
        groove_rooms = []
        try:
            for item in load_rooms():
                if item.get("branch") == "그루브 사당점":
                    room = RoomKey(
                        name=item["name"],
                        branch=item["branch"],
                        business_id=item["business_id"],
                        biz_item_id=item["biz_item_id"]
                    )
                    groove_rooms.append(room)
        except Exception as e:
            logger.warning(f"그루브 룸 로딩 실패: {e}")

        # 네이버 합주실 설정
        naver_rooms = [
            RoomKey(name="Classic", branch="비쥬합주실 3호점", business_id="917236", biz_item_id="5098039"),
            RoomKey(name="화이트룸", branch="비쥬합주실 1호점", business_id="522011", biz_item_id="3968896"),
            RoomKey(name="R룸", branch="준사운드 사당점", business_id="1384809", biz_item_id="6649826"),
        ]

        return [
            TestConfig(
                name="드림합주실 가용성 체크",
                rooms=dream_rooms,
                hour_slots=["13:00", "14:00"],
                checker_function=lambda date, slots, rooms: get_dream_availability(date, slots, rooms),
                expected_count=5
            ),
            TestConfig(
                name="그루브합주실 가용성 체크",
                rooms=groove_rooms,
                hour_slots=["20:00", "21:00", "22:00", "23:00"],
                checker_function=lambda date, slots, rooms: get_groove_availability(date, slots, rooms),
                expected_count=len(groove_rooms)
            ),
            TestConfig(
                name="네이버 합주실 가용성 체크",
                rooms=naver_rooms,
                hour_slots=["15:00", "16:00", "17:00"],
                checker_function=lambda date, slots, rooms: get_naver_availability(date, slots, rooms),
                expected_count=3
            )
        ]

    async def _run_single_test(self, config: TestConfig) -> TestResult:
        """단일 테스트 실행 - 공통 로직 추출"""
        start_time = time.time()
        error = None
        result_count = 0
        success = False

        try:
            date = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")

            # 그루브 전용 예외 처리
            if "그루브" in config.name:
                try:
                    result = await config.checker_function(date, config.hour_slots, config.rooms)
                except (GrooveLoginError, GrooveCredentialError) as e:
                    error = f"그루브 로그인 오류: {e.message} (코드: {e.error_code})"
                    return TestResult(
                        test_name=config.name,
                        execution_time=time.time() - start_time,
                        error=error,
                        result_count=0,
                        success=False
                    )
            else:
                result = await config.checker_function(date, config.hour_slots, config.rooms)

            # 결과 검증
            if result is not None:
                result_count = len(result)

                # 드림합주실 특별 검증
                if "드림" in config.name:
                    assert isinstance(result, list)
                    assert len(result) == config.expected_count
                    for room_result in result:
                        assert isinstance(room_result, RoomAvailability)

                # 네이버 합주실 특별 검증
                elif "네이버" in config.name:
                    assert isinstance(result, list)
                    assert all(hasattr(r, "available_slots") for r in result)

                success = True
                logger.info(f"{config.name} 테스트 성공: {result_count}개 결과")
            else:
                logger.warning(f"{config.name} 테스트 결과가 None입니다")

        except AssertionError as e:
            error = f"검증 실패: {str(e)}"
            logger.error(f"{config.name} 검증 실패: {e}")
        except Exception as e:
            error = traceback.format_exc()
            logger.error(f"{config.name} 예외 발생: {e}")

        execution_time = time.time() - start_time
        return TestResult(
            test_name=config.name,
            execution_time=execution_time,
            error=error,
            result_count=result_count,
            success=success
        )

    async def run_all_tests(self) -> List[TestResult]:
        """모든 테스트를 병렬로 실행"""
        logger.info("🎵 합주실 가용성 체크 성능 테스트 시작...")

        # 병렬로 모든 테스트 실행
        tasks = [self._run_single_test(config) for config in self.test_configs]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # 예외 처리된 결과들을 TestResult로 변환
        processed_results = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                processed_results.append(TestResult(
                    test_name=self.test_configs[i].name,
                    execution_time=0.0,
                    error=str(result),
                    result_count=0,
                    success=False
                ))
            else:
                processed_results.append(result)

        # 결과를 디스코드로 전송
        await self.send_results_to_discord(processed_results)

        return processed_results

    def _format_discord_message(self, results: List[TestResult]) -> str:
        """디스코드 메시지 포맷팅 - 가독성 개선"""
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        total_time = sum(r.execution_time for r in results)
        error_count = sum(1 for r in results if not r.success)
        success_count = len(results) - error_count

        # 헤더
        header = f"""🎵 **합주실 가용성 체크 성능 테스트 결과**
⏰ **테스트 시간**: {now}
⚡ **총 실행 시간**: {total_time:.4f}초
🎯 **성공/실패**: {success_count}/{error_count}개
"""

        # 개별 테스트 결과
        test_details = []
        for result in results:
            detail = f"""**{result.test_name}**
• 상태: {result.status_emoji} {"성공" if result.success else "실패"}
• 실행시간: {result.execution_time:.4f}초
• 결과 수: {result.result_count}개"""

            if result.error:
                error_preview = (result.error[:200] + "...") if len(result.error) > 200 else result.error
                detail += f"\n• 오류: ```{error_preview}```"

            test_details.append(detail)

        # 전체 요약
        success_rate = (success_count / len(results)) * 100 if results else 0
        avg_time = total_time / len(results) if results else 0

        summary = f"""📊 **전체 요약**
• 성공률: {success_rate:.1f}%
• 평균 실행시간: {avg_time:.4f}초
• 총 결과 수: {sum(r.result_count for r in results)}개"""

        return f"{header}\n\n{chr(10).join(test_details)}\n\n{summary}"

    async def send_results_to_discord(self, results: List[TestResult]):
        """테스트 결과를 디스코드로 전송 - 오류 처리 강화"""
        try:
            message = self._format_discord_message(results)
            error_count = sum(1 for r in results if not r.success)

            embed = {
                "title": "🎵 합주실 성능 테스트 완료",
                "description": message,
                "color": 0x00ff00 if error_count == 0 else (0xffaa00 if error_count < len(results) else 0xff0000),
                "timestamp": datetime.now().isoformat(),
                "footer": {"text": "합주실 가용성 모니터링 시스템 v2.0"}
            }

            response = requests.post(
                self.discord_webhook_url,
                json={"embeds": [embed]},
                timeout=15  # 타임아웃 증가
            )

            if response.status_code == 204:
                logger.info("✅ 디스코드 전송 성공")
            else:
                logger.error(f"❌ 디스코드 전송 실패: {response.status_code}, {response.text}")

        except requests.RequestException as e:
            logger.error(f"❌ 디스코드 전송 네트워크 오류: {e}")
        except Exception as e:
            logger.error(f"❌ 디스코드 전송 예외: {e}")

# 주기적 실행을 위한 스케줄러
import schedule

class PerformanceTestScheduler:
    """성능 테스트 스케줄러"""

    def __init__(self, discord_webhook_url: str):
        self.tester = RoomAvailabilityPerformanceTester(discord_webhook_url)

    def run_test_job(self):
        """스케줄러용 동기 래퍼 함수"""
        try:
            asyncio.run(self.tester.run_all_tests())
        except Exception as e:
            logger.error(f"스케줄 테스트 실행 중 오류: {e}")

    def start_scheduler(self, interval_minutes: int = 30):
        """스케줄러 시작"""
        logger.info(f"🎵 합주실 가용성 성능 테스트 스케줄러 시작 ({interval_minutes}분 간격)")
        logger.info("Ctrl+C로 종료 가능")

        # 즉시 첫 번째 테스트 실행
        logger.info("첫 번째 테스트 즉시 실행...")
        self.run_test_job()

        # 주기적 실행 설정
        schedule.every(interval_minutes).minutes.do(self.run_test_job)

        try:
            while True:
                schedule.run_pending()
                time.sleep(60)  # 1분마다 체크
        except KeyboardInterrupt:
            logger.info("\n🛑 테스트 스케줄러 종료")

def main():
    """메인 실행 함수"""
    DISCORD_WEBHOOK_URL = "YOUR_DISCORD_WEBHOOK_URL_HERE"  # 실제 웹훅 URL로 변경

    scheduler = PerformanceTestScheduler(DISCORD_WEBHOOK_URL)

    print("실행 방식을 선택하세요:")
    print("1. 한 번만 실행")
    print("2. 주기적 자동 실행 (30분 간격)")
    print("3. 사용자 정의 간격")

    choice = input("선택 (1-3): ").strip()

    if choice == "1":
        # 한 번만 실행
        scheduler.run_test_job()
    elif choice == "2":
        # 30분 간격으로 실행
        scheduler.start_scheduler(30)
    elif choice == "3":
        # 사용자 정의 간격
        try:
            interval = int(input("실행 간격(분): "))
            scheduler.start_scheduler(interval)
        except ValueError:
            print("올바른 숫자를 입력하세요.")
    else:
        print("잘못된 선택입니다.")

if __name__ == "__main__":
    main()