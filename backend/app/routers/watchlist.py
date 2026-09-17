"""CRUD de la watchlist y métricas para las tarjetas de la UI."""
import logging
import re
from concurrent.futures import ThreadPoolExecutor

from fastapi import APIRouter, Depends, HTTPException

from .. import db, engine, market
from ..auth import require_token
from ..models import (CreateGroupPayload, GroupsResponse, MoveGroupPayload,
                      SetTickerGroupPayload, TickerMetrics, WatchlistResponse)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/watchlist", tags=["watchlist"],
                   dependencies=[Depends(require_token)])

TICKER_RE = re.compile(r"^[A-Z0-9.\-]{1,10}$")
GROUP_NAME_RE = re.compile(r"^.{1,40}$")


def _metrics_for(ticker: str, ma_type: str, fast_len: int, slow_len: int) -> TickerMetrics:
    try:
        bars = market.get_bars(ticker)
        return engine.analyze(ticker, bars, ma_type, fast_len, slow_len)
    except market.MarketError as exc:
        return TickerMetrics(ticker=ticker, error=str(exc))
    except Exception as exc:  # noqa: BLE001 — un ticker roto no tumba la lista
        logger.exception("Error inesperado con %s", ticker)
        return TickerMetrics(ticker=ticker, error=f"Error interno: {exc}")


@router.get("", response_model=WatchlistResponse)
def list_watchlist() -> WatchlistResponse:
    ma_type, fast_len, slow_len = db.get_engine_settings()
    rows = db.get_watchlist()
    tickers = [row["ticker"] for row in rows]
    groups_by_ticker = {row["ticker"]: row["group_name"] for row in rows}
    # Consultas en paralelo: la mayoría sale de la caché de 5 minutos
    with ThreadPoolExecutor(max_workers=6) as pool:
        results = list(pool.map(
            lambda t: _metrics_for(t, ma_type, fast_len, slow_len), tickers))
    for r in results:
        r.group = groups_by_ticker.get(r.ticker)
    return WatchlistResponse(ma_type=ma_type, fast_len=fast_len,
                             slow_len=slow_len, tickers=results)


# ── Grupos ─────────────────────────────────────────────────
# Organizan la misma watchlist compartida en secciones colapsables (ver
# frontend/public/groups.js); no afectan el motor de cruces ni qué tickers hay.
# Se registran ANTES de "/{ticker}" porque FastAPI resuelve rutas en el orden
# en que se declaran: si "/{ticker}" fuera primero, capturaría "/groups" como
# si "groups" fuera un símbolo.
#
# Trade-off aceptado: esto reserva el segmento literal "groups" -- un ticker
# real llamado exactamente GROUPS (si existiera) no se podría agregar vía
# POST /api/watchlist/groups, porque esa ruta ahora es "crear grupo". No se
# conoce ningún ticker así; de aparecer, la salida sería agregarlo con un
# prefijo de ruta separado (ej. /api/watchlist-groups) en vez de anidarlo
# bajo /api/watchlist/{ticker}.

@router.get("/groups", response_model=GroupsResponse)
def get_groups() -> GroupsResponse:
    return GroupsResponse(groups=db.list_groups())


@router.post("/groups", response_model=GroupsResponse, status_code=201)
def add_group(payload: CreateGroupPayload) -> GroupsResponse:
    name = payload.name.strip()
    if not GROUP_NAME_RE.match(name):
        raise HTTPException(status_code=422, detail="Nombre de grupo inválido")
    if not db.create_group(name):
        raise HTTPException(status_code=409, detail=f"El grupo \"{name}\" ya existe")
    return GroupsResponse(groups=db.list_groups())


@router.put("/groups/{name}", response_model=GroupsResponse)
def edit_group(name: str, payload: CreateGroupPayload) -> GroupsResponse:
    new_name = payload.name.strip()
    if not GROUP_NAME_RE.match(new_name):
        raise HTTPException(status_code=422, detail="Nombre de grupo inválido")
    if not db.rename_group(name, new_name):
        raise HTTPException(status_code=409, detail="No se pudo renombrar el grupo")
    return GroupsResponse(groups=db.list_groups())


@router.delete("/groups/{name}", response_model=GroupsResponse)
def remove_group(name: str) -> GroupsResponse:
    if not db.delete_group(name):
        raise HTTPException(status_code=404, detail="Grupo no encontrado")
    return GroupsResponse(groups=db.list_groups())


@router.post("/groups/{name}/move", response_model=GroupsResponse)
def reorder_group(name: str, payload: MoveGroupPayload) -> GroupsResponse:
    if payload.direction not in ("up", "down"):
        raise HTTPException(status_code=422, detail="direction debe ser 'up' o 'down'")
    db.move_group(name, payload.direction)
    return GroupsResponse(groups=db.list_groups())


@router.put("/{ticker}/group", response_model=TickerMetrics)
def assign_ticker_group(ticker: str, payload: SetTickerGroupPayload) -> TickerMetrics:
    ticker = ticker.strip().upper()
    if not db.set_ticker_group(ticker, payload.group):
        raise HTTPException(status_code=404, detail="Ticker o grupo no encontrado")
    ma_type, fast_len, slow_len = db.get_engine_settings()
    metrics = _metrics_for(ticker, ma_type, fast_len, slow_len)
    metrics.group = payload.group
    return metrics


@router.post("/{ticker}", response_model=TickerMetrics, status_code=201)
def add_ticker(ticker: str) -> TickerMetrics:
    ticker = ticker.strip().upper()
    if not TICKER_RE.match(ticker):
        raise HTTPException(status_code=422, detail="Ticker inválido")
    ma_type, fast_len, slow_len = db.get_engine_settings()
    # Validar que existan datos antes de guardarlo
    metrics = _metrics_for(ticker, ma_type, fast_len, slow_len)
    if metrics.error:
        raise HTTPException(status_code=404, detail=f"Sin datos para {ticker}: {metrics.error}")
    if not db.add_ticker(ticker):
        raise HTTPException(status_code=409, detail=f"{ticker} ya está en la lista")
    baseline = engine.analyze(ticker, market.closed_bars(market.get_bars(ticker)), ma_type, fast_len, slow_len)
    if not baseline.error:
        db.update_regime(ticker, baseline.regime, baseline.cross_date)
    return metrics


@router.delete("/{ticker}", status_code=204)
def delete_ticker(ticker: str) -> None:
    if not db.remove_ticker(ticker.strip().upper()):
        raise HTTPException(status_code=404, detail="Ticker no encontrado")
