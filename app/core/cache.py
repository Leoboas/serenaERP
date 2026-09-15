"""Legacy import path for the Redis infrastructure adapter."""

from app.infrastructure.redis import get_redis, report_cache_key

__all__ = ["get_redis", "report_cache_key"]
