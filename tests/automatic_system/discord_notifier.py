# discord_notifier.py

import requests
import logging
from datetime import datetime
from typing import List, Dict, Any

# dataclasses는 performance_tester.py에 있으므로, 간단한 타입 힌팅을 위해 Any를 사용하거나
# 별도의 models.py 파일로 분리할 수도 있습니다. 여기서는 간단하게 유지합니다.
# from performance_tester import TestResult # 순환 참조를 피하기 위해 타입 힌트만 사용

logger = logging.getLogger(__name__)

class DiscordNotifier:
    """디스코드 웹훅 알림을 담당하는 클래스"""

    def __init__(self, webhook_url: str):
        if not webhook_url or "YOUR_DISCORD_WEBHOOK_URL_HERE" in webhook_url:
            raise ValueError("유효한 디스코드 웹훅 URL을 설정해야 합니다.")
        self.webhook_url = webhook_url

    def _format_discord_message(self, results: List[Any]) -> Dict[str, Any]:
        """테스트 결과를 디스코드 임베드 메시지 형식으로 포맷팅합니다."""
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        total_time = sum(r.execution_time for r in results)
        error_count = sum(1 for r in results if not r.success)
        success_count = len(results) - error_count

        # 헤더
        header = f"""⏰ **테스트 시간**: {now}
⚡ **총 실행 시간**: {total_time:.4f}초
🎯 **성공/실패**: {success_count}/{error_count}개
---"""

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

        summary = f"""---
📊 **전체 요약**
• 성공률: {success_rate:.1f}%
• 평균 실행시간: {avg_time:.4f}초
• 총 결과 수: {sum(r.result_count for r in results)}개"""

        description = f"{header}\n\n{chr(10).join(test_details)}\n\n{summary}"

        # 임베드 색상 결정
        color = 0x00ff00  # 성공 (초록색)
        if error_count > 0:
            color = 0xffaa00  # 일부 실패 (주황색)
        if error_count == len(results):
            color = 0xff0000  # 모두 실패 (빨간색)

        embed = {
            "title": "🎵 합주실 성능 테스트 완료",
            "description": description,
            "color": color,
            "timestamp": datetime.now().isoformat(),
            "footer": {"text": "합주실 가용성 모니터링 시스템 v2.0"}
        }
        return {"embeds": [embed]}


    def send_notification(self, results: List[Any]):
        """테스트 결과를 디스코드로 전송합니다."""
        try:
            payload = self._format_discord_message(results)
            response = requests.post(self.webhook_url, json=payload, timeout=15)

            if response.status_code == 204:
                logger.info("✅ 디스코드 알림 전송 성공")
            else:
                logger.error(f"❌ 디스코드 알림 전송 실패: {response.status_code}, {response.text}")

        except requests.RequestException as e:
            logger.error(f"❌ 디스코드 전송 중 네트워크 오류 발생: {e}")
        except Exception as e:
            logger.error(f"❌ 디스코드 알림 메시지 생성 또는 전송 중 예외 발생: {e}")