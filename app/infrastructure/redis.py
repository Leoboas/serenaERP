from redis.asyncio import Redis

from app.core.config import get_settings


async def get_redis() -> Redis:
    return Redis.from_url(get_settings().redis_url, decode_responses=True)


def report_cache_key(tenant_id: object) -> str:
    return f"relatorio:gastos-totais:{tenant_id}"
