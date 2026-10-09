import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from . import deps
from .config import Settings
from .dashboard import dashboard_router
from .db import clickhouse_client
from .guards import GuardError
from .ingest import ingest_router
from .store import IncidentStore
from .stream import stream_router
from .tools import tools_router


def _build_clients(settings: Settings):
    return clickhouse_client(settings), clickhouse_client(settings, read_only=True)


def create_app(settings: Settings | None = None) -> FastAPI:
    """
    Build the toolbox app and wire the shared state.

    Args:
        settings (Settings | None): Configuration; read from the environment when omitted.

    Returns:
        FastAPI: The app with the ingest, dashboard and stream routers mounted.
    """
    settings = settings or Settings.from_env(os.environ)
    db, ro_db = _build_clients(settings)
    deps.state.settings = settings
    deps.state.db = db
    deps.state.ro_db = ro_db
    deps.state.store = IncidentStore(db, broker=deps.state.broker)

    app = FastAPI(title="Rootlane toolbox")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type", "X-Admin-Token"],
    )
    app.add_exception_handler(
        GuardError, lambda request, error: JSONResponse(status_code=400, content={"detail": str(error)})
    )
    app.include_router(ingest_router)
    app.include_router(dashboard_router)
    app.include_router(stream_router)
    app.include_router(tools_router)

    @app.get("/healthz")
    def healthz() -> dict:
        return {"ok": True}

    return app
