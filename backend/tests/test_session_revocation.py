"""
NEXUS — Session revocation integration tests.

Proves the actual thing this feature is for: after logging out, the
specific token that was in use stops being accepted by the server —
not just that the browser's cookie gets cleared, which is what the
old behavior amounted to (the JWT itself kept working right up to its
natural expiry, logout or not).
"""
import pytest
import pytest_asyncio
import fakeredis.aioredis as fakeaioredis
from httpx import AsyncClient, ASGITransport
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

from app.main import app
from app.db.session import get_session
from app.core.rate_limit import login_limiter, signup_limiter, security_answer_limiter
import app.core.token_revocation as token_revocation

SIGNUP_BODY = {
    "email": "session-test@example.com",
    "password": "hunter2222",
    "name": "Session Test",
    "security_question": "First pet?",
    "security_answer": "Rex",
}


@pytest.fixture(autouse=True)
def _reset_rate_limiters():
    for limiter in (login_limiter, signup_limiter, security_answer_limiter):
        limiter._hits.clear()


@pytest.fixture(autouse=True)
def _reset_revocation_state():
    """Same reasoning as the rate limiter reset: the revoked-token store
    (whether Redis or the in-memory fallback) is module-level state that
    would otherwise leak between tests."""
    original = token_revocation.redis_client
    token_revocation._memory_revoked.clear()
    yield
    token_revocation.redis_client = original
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


@pytest.mark.asyncio
async def test_token_works_before_logout(client):
    token_revocation.redis_client = None  # exercise the in-memory path explicitly
    signup = await client.post("/api/auth/signup", json=SIGNUP_BODY)
    token = signup.json()["access_token"]

    r = await client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    assert r.json()["email"] == "session-test@example.com"


@pytest.mark.asyncio
async def test_logout_revokes_the_specific_token_used(client):
    """The core regression test: the exact token that was active at
    logout must be rejected afterward — this is the whole point of the
    feature, and it's the one thing the previous cookie-only logout
    could never do."""
    token_revocation.redis_client = None
    signup = await client.post("/api/auth/signup", json=SIGNUP_BODY)
    token = signup.json()["access_token"]

    # confirm it works first
    r = await client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200

    logout = await client.post("/api/auth/logout", headers={"Authorization": f"Bearer {token}"})
    assert logout.status_code == 200

    r = await client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_logging_out_one_session_does_not_affect_a_second_login(client):
    """Logging out on one device/browser must not silently invalidate a
    DIFFERENT session for the same user — each token has its own jti,
    revocation is per-token, not per-user."""
    token_revocation.redis_client = None
    await client.post("/api/auth/signup", json=SIGNUP_BODY)

    login_a = await client.post("/api/auth/login", json={"email": SIGNUP_BODY["email"], "password": SIGNUP_BODY["password"]})
    login_b = await client.post("/api/auth/login", json={"email": SIGNUP_BODY["email"], "password": SIGNUP_BODY["password"]})
    token_a = login_a.json()["access_token"]
    token_b = login_b.json()["access_token"]
    assert token_a != token_b  # sanity: two genuinely different tokens (different jti)

    await client.post("/api/auth/logout", headers={"Authorization": f"Bearer {token_a}"})

    r_a = await client.get("/api/auth/me", headers={"Authorization": f"Bearer {token_a}"})
    r_b = await client.get("/api/auth/me", headers={"Authorization": f"Bearer {token_b}"})
    assert r_a.status_code == 401  # revoked
    assert r_b.status_code == 200  # untouched


@pytest.mark.asyncio
async def test_revocation_works_via_redis_backend(client):
    """Same scenario as above, but exercising the real Redis-backed path
    (via fakeredis) instead of the in-memory fallback, since these are
    genuinely different code paths inside is_token_revoked/revoke_token."""
    token_revocation.redis_client = fakeaioredis.FakeRedis()

    signup = await client.post("/api/auth/signup", json=SIGNUP_BODY)
    token = signup.json()["access_token"]

    r = await client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200

    await client.post("/api/auth/logout", headers={"Authorization": f"Bearer {token}"})

    r = await client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_cookie_based_session_is_also_revoked_on_logout(client):
    """The web app's httpOnly-cookie path must get the same protection
    as the mobile Bearer-token path — both call the same underlying
    _resolve_user_id/get_current_user_id, but exercising via cookies
    specifically catches any divergence between the two code paths."""
    token_revocation.redis_client = None
    await client.post("/api/auth/signup", json=SIGNUP_BODY)
    # httpx's AsyncClient persists Set-Cookie headers automatically for
    # subsequent requests in the same client, same as a browser would.

    r = await client.get("/api/auth/me")
    assert r.status_code == 200

    logout = await client.post("/api/auth/logout")
    assert logout.status_code == 200

    r = await client.get("/api/auth/me")
    assert r.status_code == 401
