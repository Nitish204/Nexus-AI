"""
NEXUS — Two-factor auth (TOTP) integration tests.

Covers the full real flow: setup -> enable -> login now requires the
second factor -> verify with a real TOTP code -> backup codes work and
are one-time-use -> disable requires the password -> a pending-2FA
token can never be used as a real session (the security gap that was
caught and fixed while building this).
"""
import pyotp
import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

from app.main import app
from app.db.session import get_session
from app.core.rate_limit import login_limiter, signup_limiter, security_answer_limiter, totp_limiter
import app.core.token_revocation as token_revocation

SIGNUP_BODY = {
    "email": "twofa-test@example.com",
    "password": "hunter2222",
    "name": "Two FA Test",
    "security_question": "First pet?",
    "security_answer": "Rex",
}


@pytest.fixture(autouse=True)
def _reset_rate_limiters():
    for limiter in (login_limiter, signup_limiter, security_answer_limiter, totp_limiter):
        limiter._hits.clear()


@pytest.fixture(autouse=True)
def _reset_revocation_state():
    token_revocation.redis_client = None
    token_revocation._memory_revoked.clear()
    yield
    token_revocation._memory_revoked.clear()


@pytest_asyncio.fixture
async def client():
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
        yield ac
    app.dependency_overrides.clear()
    await engine.dispose()


async def _signup_and_setup_2fa(client):
    """Shared setup: signup, then /2fa/setup, returning (token, secret, backup_codes)."""
    signup = await client.post("/api/auth/signup", json=SIGNUP_BODY)
    token = signup.json()["access_token"]

    setup = await client.post("/api/auth/2fa/setup", headers={"Authorization": f"Bearer {token}"})
    assert setup.status_code == 200
    data = setup.json()
    return token, data["secret"], data["backup_codes"]


@pytest.mark.asyncio
async def test_setup_returns_secret_and_ten_backup_codes(client):
    token, secret, backup_codes = await _signup_and_setup_2fa(client)
    assert len(secret) >= 16  # base32 TOTP secrets are at least this long
    assert len(backup_codes) == 10
    assert len(set(backup_codes)) == 10  # all unique


@pytest.mark.asyncio
async def test_setup_alone_does_not_enable_2fa(client):
    """Just calling /2fa/setup must not turn 2FA on — a user who starts
    setup but never confirms with a real code must not get locked out."""
    token, secret, _ = await _signup_and_setup_2fa(client)
    login = await client.post("/api/auth/login", json={"email": SIGNUP_BODY["email"], "password": SIGNUP_BODY["password"]})
    assert login.status_code == 200
    assert "requires_2fa" not in login.json()


@pytest.mark.asyncio
async def test_enable_requires_a_correct_code(client):
    token, secret, _ = await _signup_and_setup_2fa(client)

    bad = await client.post("/api/auth/2fa/enable", json={"code": "000000"}, headers={"Authorization": f"Bearer {token}"})
    assert bad.status_code == 401

    good_code = pyotp.TOTP(secret).now()
    good = await client.post("/api/auth/2fa/enable", json={"code": good_code}, headers={"Authorization": f"Bearer {token}"})
    assert good.status_code == 200


@pytest.mark.asyncio
async def test_full_login_flow_with_2fa_enabled(client):
    """The real end-to-end path: password alone no longer completes
    login; the second factor is genuinely required."""
    token, secret, _ = await _signup_and_setup_2fa(client)
    await client.post("/api/auth/2fa/enable", json={"code": pyotp.TOTP(secret).now()}, headers={"Authorization": f"Bearer {token}"})

    login = await client.post("/api/auth/login", json={"email": SIGNUP_BODY["email"], "password": SIGNUP_BODY["password"]})
    assert login.status_code == 200
    body = login.json()
    assert body["requires_2fa"] is True
    pending_token = body["pending_token"]
    assert "access_token" not in body  # must NOT be logged in yet from password alone

    verify = await client.post("/api/auth/2fa/verify", json={"pending_token": pending_token, "code": pyotp.TOTP(secret).now()})
    assert verify.status_code == 200
    assert "access_token" in verify.json()


@pytest.mark.asyncio
async def test_wrong_totp_code_at_verify_is_rejected(client):
    token, secret, _ = await _signup_and_setup_2fa(client)
    await client.post("/api/auth/2fa/enable", json={"code": pyotp.TOTP(secret).now()}, headers={"Authorization": f"Bearer {token}"})
    login = await client.post("/api/auth/login", json={"email": SIGNUP_BODY["email"], "password": SIGNUP_BODY["password"]})
    pending_token = login.json()["pending_token"]

    verify = await client.post("/api/auth/2fa/verify", json={"pending_token": pending_token, "code": "000000"})
    assert verify.status_code == 401


@pytest.mark.asyncio
async def test_backup_code_works_and_is_single_use(client):
    token, secret, backup_codes = await _signup_and_setup_2fa(client)
    await client.post("/api/auth/2fa/enable", json={"code": pyotp.TOTP(secret).now()}, headers={"Authorization": f"Bearer {token}"})

    login = await client.post("/api/auth/login", json={"email": SIGNUP_BODY["email"], "password": SIGNUP_BODY["password"]})
    pending_token = login.json()["pending_token"]

    code_to_use = backup_codes[0]
    verify = await client.post("/api/auth/2fa/verify", json={"pending_token": pending_token, "code": code_to_use})
    assert verify.status_code == 200

    # Same backup code must not work a second time, even with a fresh
    # pending token from a new login attempt.
    login2 = await client.post("/api/auth/login", json={"email": SIGNUP_BODY["email"], "password": SIGNUP_BODY["password"]})
    pending_token2 = login2.json()["pending_token"]
    verify2 = await client.post("/api/auth/2fa/verify", json={"pending_token": pending_token2, "code": code_to_use})
    assert verify2.status_code == 401


@pytest.mark.asyncio
async def test_a_different_unused_backup_code_still_works(client):
    token, secret, backup_codes = await _signup_and_setup_2fa(client)
    await client.post("/api/auth/2fa/enable", json={"code": pyotp.TOTP(secret).now()}, headers={"Authorization": f"Bearer {token}"})

    login = await client.post("/api/auth/login", json={"email": SIGNUP_BODY["email"], "password": SIGNUP_BODY["password"]})
    pending_token = login.json()["pending_token"]
    # use the FIRST backup code
    await client.post("/api/auth/2fa/verify", json={"pending_token": pending_token, "code": backup_codes[0]})

    login2 = await client.post("/api/auth/login", json={"email": SIGNUP_BODY["email"], "password": SIGNUP_BODY["password"]})
    pending_token2 = login2.json()["pending_token"]
    # a DIFFERENT, still-unused backup code must still work
    verify2 = await client.post("/api/auth/2fa/verify", json={"pending_token": pending_token2, "code": backup_codes[1]})
    assert verify2.status_code == 200


@pytest.mark.asyncio
async def test_disable_requires_correct_password(client):
    token, secret, _ = await _signup_and_setup_2fa(client)
    await client.post("/api/auth/2fa/enable", json={"code": pyotp.TOTP(secret).now()}, headers={"Authorization": f"Bearer {token}"})

    wrong = await client.post("/api/auth/2fa/disable", json={"password": "wrong-password"}, headers={"Authorization": f"Bearer {token}"})
    assert wrong.status_code == 401

    right = await client.post("/api/auth/2fa/disable", json={"password": SIGNUP_BODY["password"]}, headers={"Authorization": f"Bearer {token}"})
    assert right.status_code == 200

    # login should now work WITHOUT requiring a second factor
    login = await client.post("/api/auth/login", json={"email": SIGNUP_BODY["email"], "password": SIGNUP_BODY["password"]})
    assert login.status_code == 200
    assert "requires_2fa" not in login.json()


@pytest.mark.asyncio
async def test_pending_token_cannot_be_used_as_a_real_session():
    """
    Regression test for a real security gap caught and fixed while
    building this feature: a 2FA-pending token is a validly-signed JWT
    (it must be, to be trustworthy at all), which means without an
    EXPLICIT purpose check, it could otherwise be presented as a normal
    Bearer token and silently accepted as a full session — completely
    defeating the point of requiring a second factor.
    """
    from app.core.security import create_2fa_pending_token
    from app.api.projects import _validate_session_payload
    from app.core.security import decode_access_token
    from fastapi import HTTPException

    pending = create_2fa_pending_token("some-user-id")
    payload = decode_access_token(pending)
    with pytest.raises(HTTPException) as exc_info:
        await _validate_session_payload(payload)
    assert exc_info.value.status_code == 401


@pytest.mark.asyncio
async def test_expired_or_garbage_pending_token_is_rejected(client):
    verify = await client.post("/api/auth/2fa/verify", json={"pending_token": "not-a-real-token", "code": "123456"})
    assert verify.status_code == 401


@pytest.mark.asyncio
async def test_totp_verify_endpoint_is_rate_limited(client):
    token, secret, _ = await _signup_and_setup_2fa(client)
    await client.post("/api/auth/2fa/enable", json={"code": pyotp.TOTP(secret).now()}, headers={"Authorization": f"Bearer {token}"})
    login = await client.post("/api/auth/login", json={"email": SIGNUP_BODY["email"], "password": SIGNUP_BODY["password"]})
    pending_token = login.json()["pending_token"]

    # totp_limiter allows 5 attempts per window (see rate_limit.py) —
    # hammer it with wrong codes past that budget.
    for _ in range(5):
        await client.post("/api/auth/2fa/verify", json={"pending_token": pending_token, "code": "000000"})
    r = await client.post("/api/auth/2fa/verify", json={"pending_token": pending_token, "code": "000000"})
    assert r.status_code == 429
