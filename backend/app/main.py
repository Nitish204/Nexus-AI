"""
NEXUS — Application entrypoint.
    uvicorn app.main:app --reload
"""
import logging
import sys
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api import analytics, api_keys, auth, code_review, deploy, github_export, graph, plugins, projects, public, push, ws
from app.core.config import get_settings
from app.db.session import init_db

logging.basicConfig(
    level=logging.INFO,
    stream=sys.stdout,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
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
app.include_router(api_keys.router)
app.include_router(public.router)
app.include_router(push.router)


@app.get("/health")
async def health():
    return {"status": "ok", "app": settings.app_name}
