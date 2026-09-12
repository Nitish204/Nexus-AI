"""
Tests for the Redis-backed rate limiter (app/core/rate_limit.py).

Covers three things directly, since they're each a distinct real
failure mode:
1. The in-memory path (used when Redis isn't configured) still works.
2. Real Redis INCR/EXPIRE counting behaves correctly (via fakeredis,
   a protocol-accurate in-memory Redis stand-in — not a mock of our
   own code, an actual Redis server implementation).
3. A genuinely unreachable Redis falls back gracefully instead of
   crashing every rate-limited request.
"""
import pytest
import fakeredis.aioredis as fakeaioredis
import redis.asyncio as aioredis

import app.core.rate_limit as rl
from app.core.rate_limit import RateLimiter


@pytest.fixture(autouse=True)
def _reset_redis_client():
    """Every test controls its own _redis_client so tests can't leak
    state or a stale connection into each other."""
    original = rl._redis_client
    yield
    rl._redis_client = original


@pytest.mark.asyncio
async def test_memory_fallback_enforces_limit_when_redis_unset():
    rl._redis_client = None
    limiter = RateLimiter(max_attempts=3, window_seconds=60, name="t1")
    key = "same-key"
    for _ in range(3):
        await limiter.check(key)
    with pytest.raises(Exception):
        await limiter.check(key)


@pytest.mark.asyncio
async def test_memory_fallback_keys_are_independent():
    rl._redis_client = None
    limiter = RateLimiter(max_attempts=1, window_seconds=60, name="t2")
    await limiter.check("user-a")
    await limiter.check("user-b")  # must not be blocked by user-a's hit


@pytest.mark.asyncio
async def test_redis_backed_counting_is_accurate():
    rl._redis_client = fakeaioredis.FakeRedis()
    limiter = RateLimiter(max_attempts=3, window_seconds=60, name="t3")
    key = "user@example.com"

    for _ in range(3):
        await limiter.check(key)
    with pytest.raises(Exception):
        await limiter.check(key)

    redis_key = limiter._redis_key(key)
    count = await rl._redis_client.get(redis_key)
    ttl = await rl._redis_client.ttl(redis_key)
    assert int(count) == 4  # 3 allowed + the 1 blocked attempt still increments
    assert 0 < ttl <= 60


@pytest.mark.asyncio
async def test_redis_backed_keys_are_independent():
    rl._redis_client = fakeaioredis.FakeRedis()
    limiter = RateLimiter(max_attempts=1, window_seconds=60, name="t4")
    await limiter.check("user-a@example.com")
    await limiter.check("user-b@example.com")  # separate budget, must not be blocked


@pytest.mark.asyncio
async def test_falls_back_to_memory_when_redis_unreachable():
    """A genuinely unreachable Redis (nothing listening) must not crash
    the request — it should silently fall back to in-memory limiting
    for that check, and keep enforcing the limit correctly."""
    rl._redis_client = aioredis.from_url(
        "redis://localhost:1/0", socket_connect_timeout=0.3, socket_timeout=0.3,
    )
    limiter = RateLimiter(max_attempts=2, window_seconds=60, name="t5")
    key = "user-during-outage"
    await limiter.check(key)
    await limiter.check(key)
    with pytest.raises(Exception):
        await limiter.check(key)


@pytest.mark.asyncio
async def test_a_real_429_is_not_swallowed_by_the_fallback_handler():
    """check()'s except-and-fallback logic must only catch Redis
    connection failures — a genuine 429 raised by _check_redis itself
    must propagate normally, not get treated as 'Redis failed, try
    memory instead' (which would silently double the effective limit)."""
    rl._redis_client = fakeaioredis.FakeRedis()
    limiter = RateLimiter(max_attempts=1, window_seconds=60, name="t6")
    key = "user@example.com"
    await limiter.check(key)
    with pytest.raises(Exception) as exc_info:
        await limiter.check(key)
    assert getattr(exc_info.value, "status_code", None) == 429
