"""
NEXUS — Minimal fixed-window rate limiter.

Deliberately in-process/in-memory rather than Redis-backed: this app
already has a redis_url configured for Celery, but tying auth
availability to Redis being up is a worse failure mode than a
per-process limiter that resets on restart. If NEXUS is ever run as
multiple backend replicas behind a load balancer, swap this for a
Redis-backed limiter (INCR + EXPIRE) so limits are shared across
instances — right now each process enforces its own limit independently.
"""
from __future__ import annotations

import time
from collections import defaultdict

from fastapi import HTTPException, Request


class RateLimiter:
    def __init__(self, max_attempts: int, window_seconds: int):
        self.max_attempts = max_attempts
        self.window_seconds = window_seconds
        self._hits: dict[str, list[float]] = defaultdict(list)

    def check(self, key: str) -> None:
        now = time.monotonic()
        window_start = now - self.window_seconds
        hits = [t for t in self._hits[key] if t > window_start]
        if len(hits) >= self.max_attempts:
            raise HTTPException(429, "Too many attempts. Please wait a few minutes and try again.")
        hits.append(now)
        self._hits[key] = hits


def _client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


login_limiter = RateLimiter(max_attempts=8, window_seconds=300)
signup_limiter = RateLimiter(max_attempts=5, window_seconds=3600)
security_answer_limiter = RateLimiter(max_attempts=6, window_seconds=600)


def enforce(limiter: RateLimiter, request: Request, extra_key: str = "") -> None:
    limiter.check(f"{_client_ip(request)}:{extra_key}")
