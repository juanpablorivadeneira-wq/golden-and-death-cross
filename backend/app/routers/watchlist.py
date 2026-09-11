"""CRUD de la watchlist y métricas para las tarjetas de la UI."""
import logging
import re
from concurrent.futures import ThreadPoolExecutor

from fastapi import APIRouter, Depends, HTTPException

from .. import db, engine, market
from ..auth import require_token
from ..models import TickerMetrics, WatchlistResponse

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/watchlist", tags=["watchlist"],
                   dependencies=[Depends(require_token)])

TICKER_RE = re.compile(r"^[A-Z0-9.\-]{1,10}$")


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
    tickers = [row["ticker"] for row in db.get_watchlist()]
    # Consultas en paralelo: la mayoría sale de la caché de 5 minutos
    with ThreadPoolExecutor(max_workers=6) as pool:
        results = list(pool.map(
            lambda t: _metrics_for(t, ma_type, fast_len, slow_len), tickers))
    return WatchlistResponse(ma_type=ma_type, fast_len=fast_len,
                             slow_len=slow_len, tickers=results)


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
    db.update_regime(ticker, metrics.regime, metrics.cross_date)
    return metrics


@router.delete("/{ticker}", status_code=204)
def delete_ticker(ticker: str) -> None:
    if not db.remove_ticker(ticker.strip().upper()):
        raise HTTPException(status_code=404, detail="Ticker no encontrado")
