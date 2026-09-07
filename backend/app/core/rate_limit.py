"""
NEXUS — Minimal fixed-window rate limiter.

Deliberately in-process/in-memory rather than Redis-backed: this app
already has a redis_url configured for Celery, but tying auth
availability to Redis being up is a worse failure mode than a
per-process limiter that resets on restart. If NEXUS is ever run as
multiple backend replicas behind a load balancer, swap this for a
Redis-backed limiter (INCR + EXPIRE) so limits are shared across
instances — right now each process enforces its own limit independently.

Two bugs fixed here vs. the original version:

1. Spoofable client IP. The original always trusted
   `X-Forwarded-For` if present. That header is just attacker-supplied
   text unless something in front of this app (a reverse proxy you
   control) strips whatever the client sent and sets it fresh. Without
   that guarantee, anyone can send a different X-Forwarded-For value on
   every request and get an unlimited number of login/signup/password-
   reset attempts — the rate limiter becomes decorative. We now only
   honor the header when `settings.trust_proxy_headers` is explicitly
   set (see app/core/config.py), and fall back to the raw socket peer
   address otherwise.

2. Unbounded memory growth. The original `_hits` dict never removed
   old keys, so every IP:email combination ever seen — including one-
   off typos, scripted abuse, or just normal traffic over time — stayed
   in memory for the life of the process. `check()` now prunes any key
   whose entries have all aged out of the window, and a lazy full sweep
   runs periodically so keys that stop being hit at all don't linger
   forever either.
"""
from __future__ import annotations

import time
from collections import defaultdict

from fastapi import HTTPException, Request

from app.core.config import get_settings

settings = get_settings()

# How often (in seconds) to do a full sweep of all keys, dropping any
# whose most recent hit is older than its own window. This runs lazily
# on top of check() calls rather than on a background timer, so it adds
# no extra moving parts / threads to reason about.
_SWEEP_INTERVAL_SECONDS = 600


class RateLimiter:
    def __init__(self, max_attempts: int, window_seconds: int):
        self.max_attempts = max_attempts
        self.window_seconds = window_seconds
        self._hits: dict[str, list[float]] = defaultdict(list)
        self._last_sweep = time.monotonic()

    def _sweep(self, now: float) -> None:
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

    def check(self, key: str) -> None:
        now = time.monotonic()
        self._sweep(now)

        window_start = now - self.window_seconds
        hits = [t for t in self._hits[key] if t > window_start]
        if len(hits) >= self.max_attempts:
            self._hits[key] = hits
            raise HTTPException(429, "Too many attempts. Please wait a few minutes and try again.")
        hits.append(now)
        self._hits[key] = hits


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


login_limiter = RateLimiter(max_attempts=8, window_seconds=300)
signup_limiter = RateLimiter(max_attempts=5, window_seconds=3600)
security_answer_limiter = RateLimiter(max_attempts=6, window_seconds=600)


def enforce(limiter: RateLimiter, request: Request, extra_key: str = "") -> None:
    limiter.check(f"{_client_ip(request)}:{extra_key}")
