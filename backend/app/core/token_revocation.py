"""
NEXUS — Session/token revocation.

Before this: logging out only ever deleted the browser's cookie. The
JWT itself kept working — anyone who'd copied the token before logout
(browser devtools, a proxy log, a compromised extension) could keep
using it right up until its natural expiry, with no way to cut it off
early. That's the actual gap "session revocation" closes: logging out
now makes that specific token stop being accepted by the server, not
just stop being sent by this one browser.

Design: every issued token gets a unique `jti` (JWT ID) claim (see
create_access_token in security.py). Logging out adds that jti to a
revoked-set in Redis, with a TTL equal to however long the token had
left before it would've expired naturally anyway — so Redis cleans up
after itself and this can never grow into an unbounded list of
every-token-ever-issued. Every authenticated request checks whether
the token's jti is on that list.

Same Redis-optional design as the rate limiter, but the fail-direction
is deliberately the opposite, and that asymmetry matters: the rate
limiter fails OPEN on a Redis outage (falls back to a real, working
in-memory limiter) because under-limiting for a few minutes is a minor
annoyance. Revocation checks also fail OPEN (treat "can't reach Redis"
as "not revoked", not as "reject every request") for a different
reason: the alternative — fail CLOSED — would mean a Redis blip locks
every single user out of an already-working session, which is a much
worse outage than the (rare, already-logged-out-elsewhere) security
gap of one stale token staying valid a little longer during that same
blip. This trade-off is a deliberate choice, not an oversight — an app
with stricter requirements (e.g. banking) might reasonably choose to
fail closed instead.
"""
from __future__ import annotations

import logging
import time

from app.core.redis_client import redis_client

logger = logging.getLogger("nexus.token_revocation")

_REVOKED_KEY_PREFIX = "revoked_jti:"

# In-memory fallback, used only while Redis is unreachable. Per-process
# (not shared across Render replicas) — strictly better than no
# revocation at all during an outage, but see the module docstring for
# why this being imperfect during an outage is an accepted trade-off,
# not a bug.
_memory_revoked: dict[str, float] = {}  # jti -> the time it can be forgotten


def _sweep_memory() -> None:
    now = time.monotonic()
    expired = [jti for jti, forget_at in _memory_revoked.items() if forget_at <= now]
    for jti in expired:
        del _memory_revoked[jti]


async def revoke_token(jti: str, ttl_seconds: int) -> None:
    """Call this on logout. `ttl_seconds` should be however long the
    token had left before its own natural expiry — no point remembering
    a revocation after the token would've stopped working anyway."""
    if ttl_seconds <= 0:
        return  # already expired on its own; nothing to revoke

    if redis_client is not None:
        try:
            await redis_client.set(f"{_REVOKED_KEY_PREFIX}{jti}", "1", ex=ttl_seconds)
            return
        except Exception as exc:
            logger.warning("Redis unavailable while revoking a token (%s) — using in-memory fallback.", exc)

    _sweep_memory()
    _memory_revoked[jti] = time.monotonic() + ttl_seconds


async def is_token_revoked(jti: str | None) -> bool:
    if not jti:
        # A token with no jti at all can't have been individually
        # revoked — this only matters for tokens issued before this
        # feature existed, during the transition. New tokens always
        # have one (see create_access_token).
        return False

    if redis_client is not None:
        try:
            return bool(await redis_client.exists(f"{_REVOKED_KEY_PREFIX}{jti}"))
        except Exception as exc:
            logger.warning("Redis unavailable while checking token revocation (%s) — failing open.", exc)

    _sweep_memory()
    return jti in _memory_revoked
