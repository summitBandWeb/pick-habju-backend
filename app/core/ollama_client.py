"""
Ollama 로컬 LLM 클라이언트

Ollama HTTP API를 통해 로컬 LLM 서버와 통신합니다.
8B 모델을 사용하여 비정형 텍스트에서 구조화된 데이터를 추출합니다.

사용법:
    client = OllamaClient()
    result = await client.generate("프롬프트")
"""

import httpx
import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)


class OllamaClient:
    """Ollama 로컬 LLM 서버와 통신하는 비동기 클라이언트.

    Rate Limit 없이 로컬에서 실행되며, GPU 가속을 지원합니다.
    연결 실패 시 None을 반환하여 Fallback 처리를 가능하게 합니다.

    httpx.AsyncClient를 재사용하여 TCP 연결 오버헤드를 최소화합니다.
    사용 후 close()를 호출하거나 async with 구문을 사용하세요.
    """

    OLLAMA_URL = "http://localhost:11434/api/generate"
    DEFAULT_MODEL = "llama3.1:8b"
    DEFAULT_TIMEOUT = 120.0  # 로컬 GPU 연산 시간 고려 (8B 모델은 CPU 시 느림)

    def __init__(
        self,
        model: str = None,
        base_url: str = None,
        timeout: float = DEFAULT_TIMEOUT
    ):
        """OllamaClient 초기화.

        Args:
            model: 사용할 모델 이름 (기본: llama3.1:8b)
            base_url: Ollama API 엔드포인트
            timeout: HTTP 요청 타임아웃 (초)
        """
        self.model = model or os.getenv("OLLAMA_MODEL", self.DEFAULT_MODEL)
        self.base_url = base_url or os.getenv("OLLAMA_URL", self.OLLAMA_URL)
        self.timeout = timeout
        self._client: Optional[httpx.AsyncClient] = None

    def _get_client(self) -> httpx.AsyncClient:
        """httpx.AsyncClient를 lazy-init으로 반환합니다."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=self.timeout)
        return self._client

    async def close(self):
        """HTTP 클라이언트를 정리합니다."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()
    
    async def generate(
        self,
        prompt: str,
        temperature: float = 0.1,
        max_tokens: int = 512
    ) -> Optional[str]:
        """프롬프트를 전송하고 JSON 형식의 응답을 받습니다.
        
        Args:
            prompt: LLM에 전송할 프롬프트
            temperature: 출력 다양성 (낮을수록 일관적, 기본 0.1)
            max_tokens: 최대 생성 토큰 수
            
        Returns:
            JSON 문자열 응답, 실패 시 None
        """
        try:
            client = self._get_client()
            response = await client.post(
                self.base_url,
                json={
                    "model": self.model,
                    "prompt": prompt,
                    "stream": False,
                    "format": "json",
                    "options": {
                        "temperature": temperature,
                        "num_predict": max_tokens,
                    }
                }
            )

            response.raise_for_status()
            result = response.json()
            response_text = result.get("response")

            if not response_text:
                logger.debug("Ollama가 빈 응답을 반환했습니다.")
                return None

            return response_text

        except httpx.HTTPStatusError as e:
            logger.warning(f"Ollama HTTP 에러 (status {e.response.status_code}): {e}")
            return None

        except httpx.ConnectError:
            logger.warning(
                "Ollama 서버에 연결할 수 없습니다. "
                "'ollama serve' 명령으로 서버를 실행하세요."
            )
            return None

        except httpx.TimeoutException:
            logger.warning(f"Ollama 요청 타임아웃 ({self.timeout}초)")
            return None

        except Exception as e:
            logger.error(f"Ollama 예상치 못한 에러: {e}", exc_info=True)
            return None

    async def is_available(self) -> bool:
        """Ollama 서버 가용성을 확인합니다.

        Returns:
            서버가 응답하면 True, 아니면 False
        """
        try:
            # base_url에서 호스트를 파싱하여 /api/tags 엔드포인트 구성
            tags_url = self.base_url.rsplit("/api/", 1)[0] + "/api/tags"
            client = self._get_client()
            response = await client.get(tags_url)
            return response.status_code == 200
        except Exception:
            return False
