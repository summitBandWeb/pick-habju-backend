# performance_tester.py

import asyncio
import time
import traceback
from datetime import datetime, timedelta
from typing import List, Optional
from dataclasses import dataclass
import logging

# 로깅 설정 (main.py에서 한 번만 설정하는 것이 더 좋습니다)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 필요한 모듈들 (실제 프로젝트 구조에 맞게 경로를 수정하세요)
from app.models.dto import RoomKey
from app.crawler.dream_checker import get_dream_availability
from app.crawler.groove_checker import get_groove_availability
from app.crawler.naver_checker import get_naver_availability
from app.exception.groove_exception import GrooveLoginError, GrooveCredentialError
from discord_notifier import DiscordNotifier  # 새로 만든 notifier 임포트


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

    def __init__(self, notifier: DiscordNotifier):
        self.notifier = notifier
        self.test_configs = self._initialize_test_configs()

    def _initialize_test_configs(self) -> List[TestConfig]:
        """테스트 설정 초기화"""
        # ... (기존과 동일한 _initialize_test_configs 코드) ...
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
            # load_rooms() 함수가 실제 프로젝트에 있다고 가정합니다.
            # 예시를 위해 임시 데이터를 사용합니다.
            mock_groove_data = [
                {"name": "A룸", "branch": "그루브 사당점", "business_id": "groove_sadang", "biz_item_id": "1"},
                {"name": "B룸", "branch": "그루브 사당점", "business_id": "groove_sadang", "biz_item_id": "2"},
            ]
            for item in mock_groove_data:  # load_rooms() 대신 mock 데이터 사용
                if item.get("branch") == "그루브 사당점":
                    groove_rooms.append(RoomKey(**item))
        except Exception as e:
            logger.warning(f"그루브 룸 로딩 실패: {e}")

        # 네이버 합주실 설정
        naver_rooms = [
            RoomKey(name="Classic", branch="비쥬합주실 3호점", business_id="917236", biz_item_id="5098039"),
            RoomKey(name="화이트룸", branch="비쥬합주실 1호점", business_id="522011", biz_item_id="3968896"),
            RoomKey(name="R룸", branch="준사운드 사당점", business_id="1384809", biz_item_id="6649826"),
        ]

        return [
            TestConfig("드림합주실 가용성 체크", dream_rooms, ["13:00", "14:00"], lambda d, s, r: get_dream_availability(d, s, r),
                       5),
            TestConfig("그루브합주실 가용성 체크", groove_rooms, ["20:00", "21:00"],
                       lambda d, s, r: get_groove_availability(d, s, r), len(groove_rooms)),
            TestConfig("네이버 합주실 가용성 체크", naver_rooms, ["15:00", "16:00"],
                       lambda d, s, r: get_naver_availability(d, s, r), 3)
        ]

    async def _run_single_test(self, config: TestConfig) -> TestResult:
        """단일 테스트 실행"""
        # ... (기존과 동일한 _run_single_test 코드) ...
        start_time = time.time()
        error = None
        result_count = 0
        success = False

        try:
            date = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")

            # 이 부분은 실제 크롤러 함수가 필요하므로, 예시에서는 mock 함수를 호출합니다.
            result = await config.checker_function(date, config.hour_slots, config.rooms)

            if result is not None:
                result_count = len(result)
                # 검증 로직 ...
                success = True
                logger.info(f"{config.name} 테스트 성공: {result_count}개 결과")
            else:
                logger.warning(f"{config.name} 테스트 결과가 None입니다")

        except (GrooveLoginError, GrooveCredentialError) as e:
            error = f"그루브 로그인 오류: {getattr(e, 'message', str(e))}"
        except AssertionError as e:
            error = f"검증 실패: {str(e)}"
            logger.error(f"{config.name} 검증 실패: {e}")
        except Exception:
            error = traceback.format_exc()
            logger.error(f"{config.name} 예외 발생:\n{error}")

        execution_time = time.time() - start_time
        return TestResult(config.name, execution_time, error, result_count, success)

    async def run_all_tests_and_notify(self):
        """모든 테스트를 병렬로 실행하고 결과를 알립니다."""
        logger.info("🎵 합주실 가용성 체크 성능 테스트 시작...")
        tasks = [self._run_single_test(config) for config in self.test_configs]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        processed_results = []
        for i, res in enumerate(results):
            if isinstance(res, Exception):
                processed_results.append(TestResult(
                    test_name=self.test_configs[i].name,
                    execution_time=0.0,
                    error=traceback.format_exc(),
                    result_count=0,
                    success=False
                ))
            else:
                processed_results.append(res)

        logger.info("🏁 모든 테스트 완료. 결과 전송 중...")
        self.notifier.send_notification(processed_results)
        return processed_results