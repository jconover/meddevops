"""FastAPI application factory."""

from contextlib import asynccontextmanager

from fastapi import FastAPI

from api.db import create_pool
from api.routes import router


def create_app(conninfo: str = "") -> FastAPI:
    """Build the app. An empty conninfo means use libpq environment variables."""

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.pool = create_pool(conninfo)
        yield
        app.state.pool.close()

    app = FastAPI(title="Telemetry API", lifespan=lifespan)
    app.include_router(router)
    return app
