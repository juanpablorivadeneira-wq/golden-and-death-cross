"""Cross Monitor — API principal.

Monta los routers, inicializa la base y arranca el scheduler de escaneo.
"""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from . import db, market, scheduler
from .config import get_settings
from .models import HealthResponse
from .routers import push, quotes, watchlist

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init_db()
    scheduler.start()
    yield
    scheduler.stop()


app = FastAPI(title="Cross Monitor API", lifespan=lifespan)
app.include_router(watchlist.router)
app.include_router(quotes.router)
app.include_router(push.router)


@app.get("/api/health", response_model=HealthResponse)
def health() -> HealthResponse:
    """Único endpoint sin autenticación (healthchecks de Docker)."""
    return HealthResponse(
        status="ok",
        last_scan=scheduler.last_scan(),
        data_source=market.active_source(),
        scan_interval_min=get_settings().scan_interval_min,
    )
