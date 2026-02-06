"""
Ollama 로컬 LLM 클라이언트

Ollama HTTP API를 통해 로컬 LLM 서버와 통신합니다.
8B 모델을 사용하여 비정형 텍스트에서 구조화된 데이터를 추출합니다.

사용법:
    client = OllamaClient()
    result = await client.generate("프롬프트")
"""

import httpx
import json
import logging
from typing import Optional

logger = logging.getLogger(__name__)


class OllamaClient:
    """Ollama 로컬 LLM 서버와 통신하는 비동기 클라이언트.
    
    Rate Limit 없이 로컬에서 실행되며, GPU 가속을 지원합니다.
    연결 실패 시 None을 반환하여 Fallback 처리를 가능하게 합니다.
    """
    
    OLLAMA_URL = "http://localhost:11434/api/generate"
    DEFAULT_MODEL = "llama3.1:8b"
    DEFAULT_TIMEOUT = 120.0  # 로컬 GPU 연산 시간 고려 (8B 모델은 CPU 시 느림)
    
    def __init__(
        self,
        model: str = DEFAULT_MODEL,
        base_url: str = OLLAMA_URL,
        timeout: float = DEFAULT_TIMEOUT
    ):
        """OllamaClient 초기화.
        
        Args:
            model: 사용할 모델 이름 (기본: llama3.1:8b)
            base_url: Ollama API 엔드포인트
            timeout: HTTP 요청 타임아웃 (초)
        """
        self.model = model
        self.base_url = base_url
        self.timeout = timeout
    
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
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    self.base_url,
                    json={
                        "model": self.model,
                        "prompt": prompt,
                        "stream": False,
                        "format": "json",  # JSON 형식 강제
                        "options": {
                            "temperature": temperature,
                            "num_predict": max_tokens,
                        }
                    }
                )
                
                response.raise_for_status()
                result = response.json()
                return result.get("response")
                
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
            logger.warning(f"Ollama 요청 실패: {e}")
            return None
    
    async def is_available(self) -> bool:
        """Ollama 서버 가용성을 확인합니다.
        
        Returns:
            서버가 응답하면 True, 아니면 False
        """
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get("http://localhost:11434/api/tags")
                return response.status_code == 200
        except Exception:
            return False
