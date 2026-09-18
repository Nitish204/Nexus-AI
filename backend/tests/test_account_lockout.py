"""
NEXUS — Account lockout integration tests.

Deliberately does NOT test this by making ACCOUNT_LOCKOUT_THRESHOLD
sequential /login calls — the existing per-IP rate limiter (8 attempts
per 5 minutes, see core/rate_limit.py) would trip first and mask what's
actually being tested here. That's correct, expected behavior in
production (the rate limiter is the fast first line of defense for a
single attacker; lockout is specifically the backstop for a
*distributed* attacker spreading guesses across many IPs) — but it
means these tests set the user's failed_login_count directly to
threshold-minus-one and then make a single request, which isolates the
lockout logic itself from the interaction with the rate limiter.
"""
import pytest
import pytest_asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import patch, AsyncMock
from httpx import AsyncClient, ASGITransport
from sqlmodel import SQLModel, select
from sqlmodel.ext.asyncio.session import AsyncSession
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

from app.main import app
from app.db.session import get_session
from app.db.models import User
from app.api.auth import ACCOUNT_LOCKOUT_THRESHOLD, ACCOUNT_LOCKOUT_MINUTES
from app.core.rate_limit import login_limiter, signup_limiter, security_answer_limiter, totp_limiter

SIGNUP_BODY = {
    "email": "lockout-test@example.com",
    "password": "hunter2222",
    "name": "Lockout Test",
    "security_question": "First pet?",
    "security_answer": "Rex",
}


@pytest.fixture(autouse=True)
def _reset_rate_limiters():
    for limiter in (login_limiter, signup_limiter, security_answer_limiter, totp_limiter):
        limiter._hits.clear()


@pytest_asyncio.fixture
async def client_and_maker():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async def override_get_session():
        async with maker() as session:
            yield session

    app.dependency_overrides[get_session] = override_get_session
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac, maker
    app.dependency_overrides.clear()
    await engine.dispose()


async def _set_failed_count(maker, email, count, locked_until=None):
    async with maker() as session:
        user = (await session.exec(select(User).where(User.email == email))).first()
        user.failed_login_count = count
        user.locked_until = locked_until
        session.add(user)
        await session.commit()


@pytest.mark.asyncio
async def test_one_wrong_password_does_not_lock_the_account(client_and_maker):
    client, maker = client_and_maker
    await client.post("/api/auth/signup", json=SIGNUP_BODY)
    r = await client.post("/api/auth/login", json={"email": SIGNUP_BODY["email"], "password": "wrong"})
    assert r.status_code == 401

    async with maker() as session:
        user = (await session.exec(select(User).where(User.email == SIGNUP_BODY["email"]))).first()
        assert user.failed_login_count == 1
        assert user.locked_until is None


@pytest.mark.asyncio
async def test_reaching_the_threshold_locks_the_account(client_and_maker):
    client, maker = client_and_maker
    await client.post("/api/auth/signup", json=SIGNUP_BODY)
    await _set_failed_count(maker, SIGNUP_BODY["email"], ACCOUNT_LOCKOUT_THRESHOLD - 1)

    r = await client.post("/api/auth/login", json={"email": SIGNUP_BODY["email"], "password": "wrong"})
    assert r.status_code == 401  # this specific attempt still reports as a normal wrong-password failure

    async with maker() as session:
        user = (await session.exec(select(User).where(User.email == SIGNUP_BODY["email"]))).first()
        assert user.locked_until is not None
        # Same SQLite-strips-timezone quirk noted in app/api/auth.py —
        # normalize before comparing, exactly as the app itself does.
        locked_until = user.locked_until.replace(tzinfo=timezone.utc) if user.locked_until.tzinfo is None else user.locked_until
        assert locked_until > datetime.now(timezone.utc)
        assert user.failed_login_count == 0  # reset once locked


@pytest.mark.asyncio
async def test_correct_password_is_rejected_while_locked(client_and_maker):
    """The actual point of lockout, distinct from rate limiting: even
    the genuinely correct password must not succeed while locked."""
    client, maker = client_and_maker
    await client.post("/api/auth/signup", json=SIGNUP_BODY)
    future_lock = datetime.now(timezone.utc) + timedelta(minutes=15)
    await _set_failed_count(maker, SIGNUP_BODY["email"], 0, locked_until=future_lock)

    r = await client.post("/api/auth/login", json={"email": SIGNUP_BODY["email"], "password": SIGNUP_BODY["password"]})
    assert r.status_code == 423


@pytest.mark.asyncio
async def test_login_succeeds_again_after_lockout_expires(client_and_maker):
    client, maker = client_and_maker
    await client.post("/api/auth/signup", json=SIGNUP_BODY)
    past_lock = datetime.now(timezone.utc) - timedelta(seconds=5)  # already expired
    await _set_failed_count(maker, SIGNUP_BODY["email"], 0, locked_until=past_lock)

    r = await client.post("/api/auth/login", json={"email": SIGNUP_BODY["email"], "password": SIGNUP_BODY["password"]})
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_successful_login_resets_failed_count(client_and_maker):
    client, maker = client_and_maker
    await client.post("/api/auth/signup", json=SIGNUP_BODY)
    await _set_failed_count(maker, SIGNUP_BODY["email"], 5)

    r = await client.post("/api/auth/login", json={"email": SIGNUP_BODY["email"], "password": SIGNUP_BODY["password"]})
    assert r.status_code == 200

    async with maker() as session:
        user = (await session.exec(select(User).where(User.email == SIGNUP_BODY["email"]))).first()
        assert user.failed_login_count == 0
        assert user.locked_until is None


@pytest.mark.asyncio
async def test_lockout_error_message_includes_wait_time(client_and_maker):
    client, maker = client_and_maker
    await client.post("/api/auth/signup", json=SIGNUP_BODY)
    future_lock = datetime.now(timezone.utc) + timedelta(minutes=ACCOUNT_LOCKOUT_MINUTES)
    await _set_failed_count(maker, SIGNUP_BODY["email"], 0, locked_until=future_lock)

    r = await client.post("/api/auth/login", json={"email": SIGNUP_BODY["email"], "password": "irrelevant"})
    assert r.status_code == 423
    assert "minute" in r.json()["detail"].lower()


@pytest.mark.asyncio
async def test_push_alert_fires_exactly_when_account_locks(client_and_maker):
    """The alert must fire the moment lockout actually triggers — not
    on every ordinary failed attempt before that point."""
    client, maker = client_and_maker
    await client.post("/api/auth/signup", json=SIGNUP_BODY)
    await _set_failed_count(maker, SIGNUP_BODY["email"], ACCOUNT_LOCKOUT_THRESHOLD - 1)

    with patch("app.api.auth.send_push_to_user", new_callable=AsyncMock) as mock_push:
        r = await client.post("/api/auth/login", json={"email": SIGNUP_BODY["email"], "password": "wrong"})
        assert r.status_code == 401
        assert mock_push.called
        call_kwargs = mock_push.call_args
        # second positional arg is user_id, third is the title
        assert "locked" in call_kwargs.args[3].lower() or "locked" in call_kwargs.args[2].lower()


@pytest.mark.asyncio
async def test_push_alert_does_not_fire_on_an_ordinary_failed_attempt(client_and_maker):
    client, maker = client_and_maker
    await client.post("/api/auth/signup", json=SIGNUP_BODY)
    # nowhere near the threshold
    await _set_failed_count(maker, SIGNUP_BODY["email"], 1)

    with patch("app.api.auth.send_push_to_user", new_callable=AsyncMock) as mock_push:
        r = await client.post("/api/auth/login", json={"email": SIGNUP_BODY["email"], "password": "wrong"})
        assert r.status_code == 401
        assert not mock_push.called


@pytest.mark.asyncio
async def test_login_still_succeeds_for_that_request_even_if_push_sending_fails(client_and_maker):
    """A broken/unreachable push service must never break the actual
    lockout behavior or crash the login response itself — it's a
    best-effort side channel, not something the request depends on."""
    client, maker = client_and_maker
    await client.post("/api/auth/signup", json=SIGNUP_BODY)
    await _set_failed_count(maker, SIGNUP_BODY["email"], ACCOUNT_LOCKOUT_THRESHOLD - 1)

    with patch("app.api.auth.send_push_to_user", new_callable=AsyncMock) as mock_push:
        mock_push.side_effect = Exception("push service unreachable")
        r = await client.post("/api/auth/login", json={"email": SIGNUP_BODY["email"], "password": "wrong"})
        # Still a normal 401 (the actual lockout logic completed fine),
        # not a 500 from the failed push attempt leaking out.
        assert r.status_code == 401

    async with maker() as session:
        user = (await session.exec(select(User).where(User.email == SIGNUP_BODY["email"]))).first()
        assert user.locked_until is not None  # lockout itself still happened correctly
