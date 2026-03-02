import httpx
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.core.ollama_client import OllamaClient


@pytest.mark.asyncio
async def test_generate_disables_after_memory_error():
    client = OllamaClient()

    response = MagicMock()
    response.status_code = 500
    response.text = '{"error":"model requires more system memory (14.1 GiB) than is available (13.3 GiB)"}'
    request = httpx.Request("POST", "http://localhost:11434/api/generate")
    memory_error = httpx.HTTPStatusError(
        "500 memory error",
        request=request,
        response=response,
    )

    fake_http_client = AsyncMock()
    fake_http_client.post.side_effect = memory_error

    with patch.object(client, "_get_client", return_value=fake_http_client):
        first = await client.generate("test prompt")
        second = await client.generate("another prompt")

    assert first is None
    assert second is None
    assert fake_http_client.post.await_count == 1


@pytest.mark.asyncio
async def test_generate_uses_gpu_only_defaults_when_forced():
    response = MagicMock()
    response.raise_for_status = MagicMock()
    response.json.return_value = {"response": "{\"ok\": true}"}

    fake_http_client = AsyncMock()
    fake_http_client.post.return_value = response

    with patch.dict("os.environ", {"OLLAMA_FORCE_GPU_ONLY": "true"}, clear=False):
        client = OllamaClient()
        with patch.object(client, "_get_client", return_value=fake_http_client):
            result = await client.generate("test prompt")

    assert result == "{\"ok\": true}"
    payload = fake_http_client.post.await_args.kwargs["json"]
    options = payload["options"]
    assert options["num_ctx"] == 8192
    assert options["num_gpu"] == -1


@pytest.mark.asyncio
async def test_generate_uses_explicit_ollama_options_env():
    response = MagicMock()
    response.raise_for_status = MagicMock()
    response.json.return_value = {"response": "{\"ok\": true}"}

    fake_http_client = AsyncMock()
    fake_http_client.post.return_value = response

    with patch.dict(
        "os.environ",
        {
            "OLLAMA_FORCE_GPU_ONLY": "true",
            "OLLAMA_NUM_CTX": "4096",
            "OLLAMA_NUM_GPU": "99",
        },
        clear=False,
    ):
        client = OllamaClient()
        with patch.object(client, "_get_client", return_value=fake_http_client):
            result = await client.generate("test prompt")

    assert result == "{\"ok\": true}"
    payload = fake_http_client.post.await_args.kwargs["json"]
    options = payload["options"]
    assert options["num_ctx"] == 4096
    assert options["num_gpu"] == 99
