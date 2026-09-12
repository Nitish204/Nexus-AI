"""
NEXUS — Application entrypoint.
    uvicorn app.main:app --reload
"""
import logging
import sys
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api import analytics, auth, code_review, deploy, github_export, graph, plugins, projects, push, ws
# NOTE: `api_keys` and `public` routers were imported here but never
# actually existed in app/api/ — this was a hard ImportError that
# crashed the app on startup before it could even bind to a port.
# They correspond to the still-unchecked roadmap item "Public,
# API-key-authenticated read endpoints (separate from the cookie-based
# web session)". Nothing in the frontend calls /api/public or an
# api-keys endpoint today, so removing the import restores boot-ability
# without silently faking a feature. Build these as a real, deliberate
# feature (new ApiKey DB model, hashed key storage, its own auth
# dependency) when you're ready to ship it — don't re-add the import
# until the files exist.
from app.core.config import get_settings
from app.db.session import engine

logging.basicConfig(
    level=logging.INFO,
    stream=sys.stdout,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Schema creation/changes are now owned entirely by Alembic
    # migrations (see migrations/), not by the app calling
    # SQLModel.metadata.create_all() on every boot. That call only ever
    # created missing tables — it silently did nothing when a table
    # already existed but a *column* had been added to the model, which
    # is exactly the gap that caused a real production outage (a column
    # existed in code but not in the live database, and every query
    # touching it crashed). Migrations are applied as a separate,
    # explicit step before the app starts — see the Render "Pre-Deploy
    # Command" set to `alembic upgrade head` — so schema drift like that
    # is caught at deploy time instead of at request time. This
    # lifespan now only verifies the database is reachable at all,
    # rather than mutating its schema.
    async with engine.connect():
        pass
    yield


app = FastAPI(title=settings.app_name, lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(projects.router)
app.include_router(analytics.router)
app.include_router(graph.router)
app.include_router(deploy.router)
app.include_router(ws.router)
app.include_router(github_export.router)
app.include_router(code_review.router)
app.include_router(plugins.router)
app.include_router(push.router)


@app.get("/health")
async def health():
    return {"status": "ok", "app": settings.app_name}
