"""
NEXUS — API key integration tests.

Covers creating a key (raw value shown once), using it to actually
authenticate a real protected endpoint (not just the key-management
endpoints themselves), revoking it, and the two things most likely to
be silently wrong in a hash-based lookup scheme: a slightly-wrong key
must not match, and a revoked key must stop working immediately.
"""
import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

from app.main import app
from app.db.session import get_session
from app.core.rate_limit import login_limiter, signup_limiter, security_answer_limiter, totp_limiter

SIGNUP_BODY = {
    "email": "apikey-test@example.com",
    "password": "hunter2222",
    "name": "API Key Test",
    "security_question": "First pet?",
    "security_answer": "Rex",
}


@pytest.fixture(autouse=True)
def _reset_rate_limiters():
    for limiter in (login_limiter, signup_limiter, security_answer_limiter, totp_limiter):
        limiter._hits.clear()


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


async def _signup(client):
    signup = await client.post("/api/auth/signup", json=SIGNUP_BODY)
    return signup.json()["access_token"]


@pytest.mark.asyncio
async def test_create_key_returns_raw_value_once(client):
    session_token = await _signup(client)
    r = await client.post(
        "/api/auth/api-keys", json={"name": "CI key"},
        headers={"Authorization": f"Bearer {session_token}"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["key"].startswith("nxs_")
    assert body["name"] == "CI key"


@pytest.mark.asyncio
async def test_listing_keys_never_exposes_the_raw_value(client):
    session_token = await _signup(client)
    await client.post("/api/auth/api-keys", json={"name": "k1"}, headers={"Authorization": f"Bearer {session_token}"})

    r = await client.get("/api/auth/api-keys", headers={"Authorization": f"Bearer {session_token}"})
    assert r.status_code == 200
    keys = r.json()
    assert len(keys) == 1
    assert "key" not in keys[0]
    assert "key_hash" not in keys[0]
    assert keys[0]["key_prefix"].startswith("nxs_")


@pytest.mark.asyncio
async def test_api_key_actually_authenticates_a_real_protected_endpoint(client):
    """The core proof: this isn't just a management CRUD feature, the
    key genuinely works as a credential on a real, unrelated endpoint —
    GET /api/projects, authenticated via get_current_user_id, the same
    dependency every other protected route in the app uses."""
    session_token = await _signup(client)
    create = await client.post(
        "/api/auth/api-keys", json={"name": "CI key"},
        headers={"Authorization": f"Bearer {session_token}"},
    )
    raw_key = create.json()["key"]

    # Create a project via the normal session first...
    await client.post("/api/projects", json={"name": "Test Project", "description": ""},
                       headers={"Authorization": f"Bearer {session_token}"})

    # ...then fetch it using ONLY the API key, no session/cookie at all.
    r = await client.get("/api/projects", headers={"X-API-Key": raw_key})
    assert r.status_code == 200
    projects = r.json()
    assert len(projects) == 1
    assert projects[0]["name"] == "Test Project"


@pytest.mark.asyncio
async def test_wrong_api_key_is_rejected(client):
    session_token = await _signup(client)
    await client.post("/api/auth/api-keys", json={"name": "k1"}, headers={"Authorization": f"Bearer {session_token}"})

    r = await client.get("/api/projects", headers={"X-API-Key": "nxs_totally-made-up-key-value-xyz"})
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_a_key_with_correct_prefix_but_wrong_secret_is_rejected(client):
    """Specifically exercises the prefix-lookup-then-verify path: a
    presented key sharing a real prefix but differing later must still
    fail — proves the full key is genuinely checked, not just the
    prefix used for the database lookup."""
    session_token = await _signup(client)
    create = await client.post(
        "/api/auth/api-keys", json={"name": "k1"}, headers={"Authorization": f"Bearer {session_token}"}
    )
    raw_key = create.json()["key"]
    tampered = raw_key[:-1] + ("a" if raw_key[-1] != "a" else "b")

    r = await client.get("/api/projects", headers={"X-API-Key": tampered})
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_revoked_key_stops_working_immediately(client):
    session_token = await _signup(client)
    create = await client.post(
        "/api/auth/api-keys", json={"name": "k1"}, headers={"Authorization": f"Bearer {session_token}"}
    )
    raw_key = create.json()["key"]
    key_id = create.json()["id"]

    r = await client.get("/api/projects", headers={"X-API-Key": raw_key})
    assert r.status_code == 200

    revoke = await client.delete(f"/api/auth/api-keys/{key_id}", headers={"Authorization": f"Bearer {session_token}"})
    assert revoke.status_code == 200

    r = await client.get("/api/projects", headers={"X-API-Key": raw_key})
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_cannot_revoke_another_users_key(client):
    session_token = await _signup(client)
    create = await client.post(
        "/api/auth/api-keys", json={"name": "k1"}, headers={"Authorization": f"Bearer {session_token}"}
    )
    key_id = create.json()["id"]

    other_signup = {**SIGNUP_BODY, "email": "someone-else@example.com"}
    other_token_resp = await client.post("/api/auth/signup", json=other_signup)
    other_token = other_token_resp.json()["access_token"]

    r = await client.delete(f"/api/auth/api-keys/{key_id}", headers={"Authorization": f"Bearer {other_token}"})
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_using_an_api_key_updates_last_used_at(client):
    session_token = await _signup(client)
    create = await client.post(
        "/api/auth/api-keys", json={"name": "k1"}, headers={"Authorization": f"Bearer {session_token}"}
    )
    raw_key = create.json()["key"]
    key_id = create.json()["id"]

    before = await client.get("/api/auth/api-keys", headers={"Authorization": f"Bearer {session_token}"})
    assert before.json()[0]["last_used_at"] is None

    await client.get("/api/projects", headers={"X-API-Key": raw_key})

    after = await client.get("/api/auth/api-keys", headers={"Authorization": f"Bearer {session_token}"})
    assert after.json()[0]["last_used_at"] is not None
