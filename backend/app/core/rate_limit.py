"""
NEXUS — Rate limiter: Redis-backed when available, in-memory otherwise.

This is a fixed-window limiter backed by Redis's INCR + EXPIRE, so
limits are shared correctly across multiple backend replicas — the
previous in-memory-only version gave each process its own separate
budget, so scaling Render to 2+ instances silently weakened every
limit (an attacker could get N times the allowed attempts, one set per
instance, just by chance of which instance handled each request).

Falls back to the original in-memory implementation, per-call, if
Redis isn't configured or a request to it fails for any reason —
deliberately per-call rather than a one-time "give up on Redis
forever" flag, so a transient Redis blip degrades gracefully instead
of either taking down auth entirely or requiring a restart to recover
once Redis comes back. This also means the app works with zero setup
in local dev (no Redis needed) and upgrades automatically the moment
REDIS_URL points at a real instance — no code changes needed either way.

The INCR-then-EXPIRE pattern is a very standard, "good enough" fixed
window for this purpose (a login/signup limiter), not a perfectly
atomic sliding window — there's a tiny theoretical race on the very
first hit in a window between the INCR and the EXPIRE call where a
crash could leave a key with no TTL, but Redis's own key eviction and
the next natural expiry-driven reset bound how bad that can ever get,
and it's a standard accepted trade-off for rate limiting specifically
(unlike, say, financial transaction counting, where it wouldn't be).
"""
from __future__ import annotations

import logging
import time
from collections import defaultdict

import redis.asyncio as aioredis
from fastapi import HTTPException, Request

from app.core.config import get_settings

settings = get_settings()
logger = logging.getLogger("nexus.rate_limit")

_SWEEP_INTERVAL_SECONDS = 600  # in-memory fallback's own housekeeping, see RateLimiter._sweep

# One shared Redis client for the whole process. redis-py's async client
# is lazy — creating it does not open a network connection by itself;
# the connection is only actually attempted on the first real command,
# and every subsequent command reuses the pool. A short timeout keeps a
# genuinely-down Redis from making every request hang.
_redis_client: aioredis.Redis | None = None
if settings.redis_url:
    _redis_client = aioredis.from_url(
        settings.redis_url, socket_connect_timeout=1.5, socket_timeout=1.5,
    )


class RateLimiter:
    def __init__(self, max_attempts: int, window_seconds: int, name: str):
        self.max_attempts = max_attempts
        self.window_seconds = window_seconds
        self.name = name  # part of the Redis key, keeps different limiters' counters separate
        # In-memory fallback store — identical to the pre-Redis version.
        self._hits: dict[str, list[float]] = defaultdict(list)
        self._last_sweep = time.monotonic()

    def _redis_key(self, key: str) -> str:
        return f"ratelimit:{self.name}:{key}"

    async def _check_redis(self, key: str) -> None:
        redis_key = self._redis_key(key)
        # INCR both creates the key at 1 and increments an existing one,
        # atomically, in a single round trip.
        count = await _redis_client.incr(redis_key)
        if count == 1:
            # Only the request that just created this window sets its
            # expiry — every later hit in the same window just
            # increments, which is what keeps this a *fixed* window
            # (each window is exactly window_seconds long from its
            # first hit) rather than a sliding one that never settles.
            await _redis_client.expire(redis_key, self.window_seconds)
        if count > self.max_attempts:
            raise HTTPException(429, "Too many attempts. Please wait a few minutes and try again.")

    def _sweep_memory(self, now: float) -> None:
        if now - self._last_sweep < _SWEEP_INTERVAL_SECONDS:
            return
        window_start = now - self.window_seconds
        stale_keys = [
            key for key, hits in self._hits.items()
            if not hits or max(hits) <= window_start
        ]
        for key in stale_keys:
            del self._hits[key]
        self._last_sweep = now

    def _check_memory(self, key: str) -> None:
        now = time.monotonic()
        self._sweep_memory(now)
        window_start = now - self.window_seconds
        hits = [t for t in self._hits[key] if t > window_start]
        if len(hits) >= self.max_attempts:
            self._hits[key] = hits
            raise HTTPException(429, "Too many attempts. Please wait a few minutes and try again.")
        hits.append(now)
        self._hits[key] = hits

    async def check(self, key: str) -> None:
        if _redis_client is not None:
            try:
                await self._check_redis(key)
                return
            except HTTPException:
                raise  # a real "too many attempts" — not a Redis failure, don't fall back
            except Exception as exc:
                logger.warning(
                    "Redis rate-limit check failed (%s) — falling back to in-memory for this request.",
                    exc,
                )
        self._check_memory(key)


def _client_ip(request: Request) -> str:
    if settings.trust_proxy_headers:
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            # The header can be a comma-separated chain
            # (client, proxy1, proxy2, ...) appended to by each hop.
            # The leftmost entry is only trustworthy if your edge proxy
            # is the one appending it after stripping whatever the
            # client sent — which is exactly what trust_proxy_headers
            # is meant to assert is true.
            return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


login_limiter = RateLimiter(max_attempts=8, window_seconds=300, name="login")
signup_limiter = RateLimiter(max_attempts=5, window_seconds=3600, name="signup")
security_answer_limiter = RateLimiter(max_attempts=6, window_seconds=600, name="security_answer")


async def enforce(limiter: RateLimiter, request: Request, extra_key: str = "") -> None:
    await limiter.check(f"{_client_ip(request)}:{extra_key}")
