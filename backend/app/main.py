"""OmniAI backend entry point.

Run:  uvicorn app.main:app --host 0.0.0.0 --port 8000
"""
from __future__ import annotations

from contextlib import asynccontextmanager
from fastapi import FastAPI

from .api.routes import router
from .config import API_PREFIX, APP_NAME
from .security import audit
from .observability.metrics import MetricsMiddleware
from .database import db


@asynccontextmanager
async def lifespan(_: FastAPI):
    audit.log("system", "server_started", {"app": APP_NAME})
    try:
        yield
    finally:
        audit.log("system", "server_stopped", {"app": APP_NAME})


app = FastAPI(title=APP_NAME, version="1.0.0", lifespan=lifespan)
app.add_middleware(MetricsMiddleware)
app.include_router(router, prefix=API_PREFIX)


@app.get("/")
def root() -> dict:
    return {"app": APP_NAME, "docs": "/docs", "api": API_PREFIX, "health": "/healthz", "ready": "/readyz"}


@app.get("/healthz")
def healthz() -> dict:
    return {"ok": True, "app": APP_NAME}


@app.get("/readyz")
def readyz() -> dict:
    schema = db.schema_info()
    ready = schema.get("current_version") == schema.get("target_version")
    return {"ok": ready, "schema": schema}
