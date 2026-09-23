"""
NEXUS — Error tracking (Sentry) setup.

Kept as its own module rather than inlined in main.py so it can be
imported and asserted on from tests without booting the whole app, and
so the "is this configured" logic lives in exactly one place.

Uptime monitoring is deliberately NOT implemented as in-process code:
an uptime check only has value if it runs somewhere that isn't this
process (otherwise the process crashing takes the monitor down with
it). Instead, `/health` (liveness: "is the process up") and
`/health/ready` (readiness: "can it actually serve requests — DB and
Redis reachable") in app/main.py are the two endpoints an external
service (UptimeRobot, Better Stack, Render's own health checks, a k8s
liveness/readiness probe) should poll. See README.md's Observability
section for the recommended check configuration.
"""
from __future__ import annotations

import logging

from app.core.config import get_settings

logger = logging.getLogger("nexus.observability")
settings = get_settings()

_initialized = False


def is_sentry_enabled() -> bool:
    return bool(settings.sentry_dsn)


def init_sentry() -> bool:
    """
    Idempotent. Returns True if Sentry is active after this call.

    No-ops (and logs once, at INFO not WARNING — an unset DSN in dev/
    test is completely normal, not a misconfiguration) when
    SENTRY_DSN isn't set, so this is always safe to call unconditionally
    from the app's lifespan/startup regardless of environment.
    """
    global _initialized
    if _initialized:
        return is_sentry_enabled()

    if not settings.sentry_dsn:
        logger.info("SENTRY_DSN not set — error tracking disabled for this process.")
        _initialized = True
        return False

    try:
        import sentry_sdk
        from sentry_sdk.integrations.fastapi import FastApiIntegration
        from sentry_sdk.integrations.starlette import StarletteIntegration
        from sentry_sdk.integrations.logging import LoggingIntegration
    except ImportError:
        # sentry-sdk is an optional prod dependency (see requirements.txt);
        # missing it should degrade to "no error tracking", never crash boot.
        logger.warning(
            "SENTRY_DSN is set but the sentry-sdk package isn't installed — "
            "error tracking is disabled. Run `pip install sentry-sdk[fastapi]`."
        )
        _initialized = True
        return False

    sentry_sdk.init(
        dsn=settings.sentry_dsn,
        environment=settings.environment,
        release=settings.release_version,
        traces_sample_rate=settings.sentry_traces_sample_rate,
        profiles_sample_rate=settings.sentry_profiles_sample_rate,
        integrations=[
            StarletteIntegration(transaction_style="endpoint"),
            FastApiIntegration(transaction_style="endpoint"),
            # Captures logging.error(...)/exception(...) calls (e.g. the
            # `logger.error(..., exc_info=True)` calls already scattered
            # through the agents/orchestrator) as Sentry events too, not
            # just uncaught exceptions that bubble out of a request.
            LoggingIntegration(level=logging.INFO, event_level=logging.ERROR),
        ],
        # Request bodies routinely contain feature requests typed by the
        # user and, more sensitively, auth payloads — don't attach them
        # to error events by default.
        send_default_pii=False,
    )
    logger.info("Sentry initialized (environment=%s, release=%s).", settings.environment, settings.release_version)
    _initialized = True
    return True
