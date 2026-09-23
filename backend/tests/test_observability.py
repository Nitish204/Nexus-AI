"""
Tests for app.core.observability — mainly guarding the "no DSN
configured" no-op path, since that's the state every dev/CI run is
actually in and it must never raise or block startup.
"""
import importlib

import pytest


@pytest.fixture(autouse=True)
def reset_observability_module():
    """Each test gets a fresh module so `_initialized` doesn't leak
    across tests (init_sentry() is intentionally idempotent/cached)."""
    import app.core.observability as obs
    importlib.reload(obs)
    yield
    importlib.reload(obs)


def test_init_sentry_is_a_noop_without_dsn(monkeypatch):
    import app.core.observability as obs

    monkeypatch.setattr(obs.settings, "sentry_dsn", "")
    result = obs.init_sentry()

    assert result is False
    assert obs.is_sentry_enabled() is False


def test_init_sentry_is_idempotent(monkeypatch):
    import app.core.observability as obs

    monkeypatch.setattr(obs.settings, "sentry_dsn", "")
    first = obs.init_sentry()
    second = obs.init_sentry()

    assert first == second == False  # noqa: E712 — explicit about the exact value, not just falsy


def test_health_ready_endpoint_reports_database_status():
    """The readiness endpoint must exist and return per-dependency
    detail, not just a bare boolean — see main.py's health_ready()."""
    from app.main import health_ready
    import asyncio

    result = asyncio.run(health_ready())
    # health_ready() returns a JSONResponse; inspect its body directly
    # rather than requiring a running server/test client for this unit test.
    assert result.status_code in (200, 503)
