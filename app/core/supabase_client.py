import asyncio
from functools import lru_cache
from supabase import create_client, create_async_client, Client, ClientOptions
from supabase.lib.client_options import AsyncClientOptions
from supabase._async.client import AsyncClient
from app.core.config import SUPABASE_URL, SUPABASE_KEY

@lru_cache
def get_supabase_client() -> Client:
    if not SUPABASE_URL or not SUPABASE_KEY:
        raise ValueError("SUPABASE_URL and SUPABASE_KEY must be set in environment variables")
    options = ClientOptions(
        schema="public",
        auto_refresh_token=True,
        persist_session=True,
    )
    return create_client(SUPABASE_URL, SUPABASE_KEY, options=options)


_async_client: AsyncClient | None = None
_async_client_lock = asyncio.Lock()


async def get_async_supabase_client() -> AsyncClient:
    global _async_client
    if _async_client is None:
        async with _async_client_lock:
            if _async_client is None:
                if not SUPABASE_URL or not SUPABASE_KEY:
                    raise ValueError("SUPABASE_URL and SUPABASE_KEY must be set in environment variables")
                options = AsyncClientOptions(
                    schema="public",
                    auto_refresh_token=True,
                    persist_session=True,
                    postgrest_client_timeout=10,
                )
                _async_client = await create_async_client(SUPABASE_URL, SUPABASE_KEY, options=options)
    return _async_client


# Backward compatibility alias
supabase = get_supabase_client()
