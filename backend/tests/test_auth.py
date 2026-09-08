"""
NEXUS — Auth integration tests.

This file didn't exist before — auth.py's actual HTTP endpoints
(signup/login/OAuth) were never integration-tested, only unit-tested
indirectly via other suites. That gap is exactly how the email
case-sensitivity bug went unnoticed: nothing exercised signup and
login together with realistic mixed-case input.
"""
import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

from app.main import app
from app.db.session import get_session
from app.core.rate_limit import login_limiter, signup_limiter, security_answer_limiter

SIGNUP_BODY = {
    "email": "Bob@Gmail.com",
    "password": "hunter2222",
    "name": "Bob",
    "security_question": "First pet?",
    "security_answer": "Rex",
}


@pytest.fixture(autouse=True)
def _reset_rate_limiters():
    """
    The rate limiters in app.core.rate_limit are module-level
    singletons, shared across every test in this whole pytest process —
    not reset just because a test's DB fixture tears down. Without
    this, running the full file back-to-back can trip signup_limiter's
    genuine 5-per-hour cap purely from test volume, which looks like a
    mysterious failure in a *later*, unrelated test. This resets all
    three before each test so every test starts with a clean budget,
    the same as it would against a real server that's been idle.
    """
    for limiter in (login_limiter, signup_limiter, security_answer_limiter):
        limiter._hits.clear()
    yield


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
async def test_signup_stores_email_lowercased(client):
    r = await client.post("/api/auth/signup", json=SIGNUP_BODY)
    assert r.status_code == 200
    assert r.json()["user"]["email"] == "bob@gmail.com"


@pytest.mark.asyncio
async def test_login_with_different_case_than_signup_succeeds(client):
    """
    Regression test for the real bug: signing up as "Bob@Gmail.com" and
    logging in as "bob@gmail.com" (or any other casing) must succeed
    with the correct password — Postgres text comparison is
    case-sensitive by default, so without normalization this silently
    fails with "Invalid email or password" despite a correct password.
    """
    await client.post("/api/auth/signup", json=SIGNUP_BODY)

    r = await client.post("/api/auth/login", json={"email": "bob@gmail.com", "password": "hunter2222"})
    assert r.status_code == 200

    r = await client.post("/api/auth/login", json={"email": "BOB@GMAIL.COM", "password": "hunter2222"})
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_signup_with_different_case_email_is_rejected_as_duplicate(client):
    """
    Regression test: without normalization, "Bob@Gmail.com" and
    "bob@gmail.com" were treated as two different people, letting the
    same real email create multiple unrelated accounts.
    """
    await client.post("/api/auth/signup", json=SIGNUP_BODY)

    duplicate = dict(SIGNUP_BODY, email="bob@gmail.com")
    r = await client.post("/api/auth/signup", json=duplicate)
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_security_question_lookup_is_case_insensitive(client):
    await client.post("/api/auth/signup", json=SIGNUP_BODY)
    r = await client.get("/api/auth/security-question", params={"email": "BOB@gmail.com"})
    assert r.status_code == 200
    assert r.json()["security_question"] == "First pet?"


@pytest.mark.asyncio
async def test_password_reset_works_with_different_case_email(client):
    await client.post("/api/auth/signup", json=SIGNUP_BODY)
    r = await client.post(
        "/api/auth/reset-password-direct",
        json={"email": "BOB@GMAIL.COM", "security_answer": "Rex", "new_password": "newpass123"},
    )
    assert r.status_code == 200

    r = await client.post("/api/auth/login", json={"email": "bob@gmail.com", "password": "newpass123"})
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_wrong_password_still_rejected(client):
    """Sanity check the normalization fix didn't accidentally make login too permissive."""
    await client.post("/api/auth/signup", json=SIGNUP_BODY)
    r = await client.post("/api/auth/login", json={"email": "bob@gmail.com", "password": "totally-wrong"})
    assert r.status_code == 401
