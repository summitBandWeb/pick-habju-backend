"""
Async client for Ollama local LLM API.
"""

import logging
import os
from typing import Any, Dict, Optional

import httpx

logger = logging.getLogger(__name__)


class OllamaClient:
    """Async client for communicating with an Ollama server."""

    OLLAMA_URL = "http://localhost:11434/api/generate"
    DEFAULT_MODEL = "llama3.1:8b"
    DEFAULT_TIMEOUT = 120.0
    DEFAULT_GPU_ONLY_NUM_CTX = 8192

    FORCE_GPU_ONLY_ENV = "OLLAMA_FORCE_GPU_ONLY"
    NUM_CTX_ENV = "OLLAMA_NUM_CTX"
    NUM_GPU_ENV = "OLLAMA_NUM_GPU"

    def __init__(
        self,
        model: str = None,
        base_url: str = None,
        timeout: float = DEFAULT_TIMEOUT,
    ):
        self.model = model or os.getenv("OLLAMA_MODEL", self.DEFAULT_MODEL)
        self.base_url = base_url or os.getenv("OLLAMA_URL", self.OLLAMA_URL)
        self.timeout = timeout

        self.force_gpu_only = self._get_bool_env(self.FORCE_GPU_ONLY_ENV, default=False)
        self.num_ctx = self._get_int_env(self.NUM_CTX_ENV)
        self.num_gpu = self._get_int_env(self.NUM_GPU_ENV)

        if self.force_gpu_only and self.num_ctx is None:
            self.num_ctx = self.DEFAULT_GPU_ONLY_NUM_CTX
        if self.force_gpu_only and self.num_gpu is None:
            # In Ollama, -1 means offload as many layers as possible.
            self.num_gpu = -1

        self._client: Optional[httpx.AsyncClient] = None
        self._disabled_reason: Optional[str] = None

    @staticmethod
    def _get_bool_env(name: str, default: bool = False) -> bool:
        raw = os.getenv(name)
        if raw is None:
            return default
        return raw.strip().lower() in {"1", "true", "yes", "on"}

    @staticmethod
    def _get_int_env(name: str) -> Optional[int]:
        raw = os.getenv(name)
        if raw is None or raw.strip() == "":
            return None
        try:
            return int(raw)
        except ValueError:
            logger.warning("Invalid int env value ignored: %s=%s", name, raw)
            return None

    def _build_options(self, temperature: float, max_tokens: int) -> Dict[str, Any]:
        options: Dict[str, Any] = {
            "temperature": temperature,
            "num_predict": max_tokens,
        }
        if self.num_ctx is not None:
            options["num_ctx"] = self.num_ctx
        if self.num_gpu is not None:
            options["num_gpu"] = self.num_gpu
        return options

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=self.timeout)
        return self._client

    async def close(self):
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
        max_tokens: int = 512,
    ) -> Optional[str]:
        if self._disabled_reason:
            logger.debug("Ollama generate skipped: %s", self._disabled_reason)
            return None

        try:
            client = self._get_client()
            response = await client.post(
                self.base_url,
                json={
                    "model": self.model,
                    "prompt": prompt,
                    "stream": False,
                    "format": "json",
                    "options": self._build_options(temperature, max_tokens),
                },
            )

            response.raise_for_status()
            result = response.json()
            response_text = result.get("response")

            if not response_text:
                logger.debug("Ollama returned an empty response.")
                return None

            return response_text

        except httpx.HTTPStatusError as e:
            response_text = e.response.text if e.response is not None else ""
            if "requires more system memory" in response_text:
                self._disabled_reason = "insufficient system memory for configured model"
                logger.warning(
                    "Ollama disabled for this process: %s",
                    self._disabled_reason,
                )
            status_code = e.response.status_code if e.response is not None else "unknown"
            logger.warning("Ollama HTTP error (status %s): %s", status_code, e)
            return None

        except httpx.ConnectError:
            logger.warning(
                "Cannot connect to Ollama server. Start it with 'ollama serve'."
            )
            return None

        except httpx.TimeoutException:
            logger.warning("Ollama request timeout (%ss)", self.timeout)
            return None

        except Exception as e:
            logger.error("Unexpected Ollama error: %s", e, exc_info=True)
            return None

    async def is_available(self) -> bool:
        try:
            tags_url = self.base_url.rsplit("/api/", 1)[0] + "/api/tags"
            client = self._get_client()
            response = await client.get(tags_url)
            return response.status_code == 200
        except Exception:
            return False
