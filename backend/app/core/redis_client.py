"""
NEXUS — One shared Redis client for the whole process.

Both the rate limiter (app/core/rate_limit.py) and session revocation
(app/core/token_revocation.py) need Redis for the same underlying
reason — a value that must be shared correctly across however many
backend replicas Render runs, not kept in one process's memory. They
share this single client/connection pool rather than each opening
their own, since there's no reason to hold two separate pools open
against the same Redis instance.

redis-py's async client is lazy — creating it does not open a network
connection by itself; the connection is only actually attempted on the
first real command, and every subsequent command reuses the pool. A
short timeout keeps a genuinely-down Redis from making every request
hang rather than failing fast.
"""
import redis.asyncio as aioredis

from app.core.config import get_settings

settings = get_settings()

redis_client: aioredis.Redis | None = None
if settings.redis_url:
    redis_client = aioredis.from_url(
        settings.redis_url, socket_connect_timeout=1.5, socket_timeout=1.5,
    )
