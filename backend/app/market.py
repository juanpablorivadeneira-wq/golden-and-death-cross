"""Descarga de datos de mercado: yfinance (primaria) o Twelve Data (si hay clave).

Caché en memoria con TTL de 5 minutos por ticker y reintentos con backoff
exponencial. Los errores se propagan como MarketError; nunca deben tumbar
el scheduler ni los endpoints (cada capa los captura por ticker).
"""
import threading
from pathlib import Path
import time
import logging

import httpx

from .config import get_settings
from .models import Bar

logger = logging.getLogger(__name__)

CACHE_TTL_SECONDS = 300
MAX_RETRIES = 3
HISTORY_YEARS = 2

_cache: dict[str, tuple[float, list[Bar]]] = {}
_cache_lock = threading.Lock()
_yahoo_initialized = False


class MarketError(Exception):
    """Error al obtener datos de mercado para un ticker."""


def active_source() -> str:
    return "twelvedata" if get_settings().twelve_data_key else "yahoo"


def _fetch_yfinance(ticker: str) -> list[Bar]:
    import yfinance as yf

    global _yahoo_initialized
    with _cache_lock:
        if not _yahoo_initialized:
            cache_dir = Path(get_settings().db_path).parent / "yfinance-cache"
            yf.set_tz_cache_location(str(cache_dir))
            _yahoo_initialized = True

    df = yf.Ticker(ticker).history(period=f"{HISTORY_YEARS}y", interval="1d",
                                   auto_adjust=False)
    if df is None or df.empty:
        raise MarketError(f"Sin datos de Yahoo para {ticker}")
    bars: list[Bar] = []
    for idx, row in df.iterrows():
        if row.isna().any():
            continue
        bars.append(Bar(
            t=int(idx.timestamp()),
            o=float(row["Open"]), h=float(row["High"]),
            l=float(row["Low"]), c=float(row["Close"]),
        ))
    return bars


def _fetch_twelvedata(ticker: str) -> list[Bar]:
    key = get_settings().twelve_data_key
    url = ("https://api.twelvedata.com/time_series"
           f"?symbol={ticker}&interval=1day&outputsize=600&apikey={key}")
    resp = httpx.get(url, timeout=15)
    resp.raise_for_status()
    data = resp.json()
    if data.get("status") == "error" or "values" not in data:
        raise MarketError(data.get("message", f"Sin datos de Twelve Data para {ticker}"))
    bars = []
    # Twelve Data entrega del más reciente al más antiguo
    for v in reversed(data["values"]):
        ts = int(time.mktime(time.strptime(v["datetime"], "%Y-%m-%d")))
        bars.append(Bar(t=ts, o=float(v["open"]), h=float(v["high"]),
                        l=float(v["low"]), c=float(v["close"])))
    return bars


def get_bars(ticker: str, force: bool = False) -> list[Bar]:
    """Barras OHLC diarias (2 años aprox.) con caché TTL y reintentos."""
    ticker = ticker.upper()
    now = time.monotonic()
    with _cache_lock:
        hit = _cache.get(ticker)
        if hit and not force and now - hit[0] < CACHE_TTL_SECONDS:
            return hit[1]

    fetch = _fetch_twelvedata if get_settings().twelve_data_key else _fetch_yfinance
    last_err: Exception | None = None
    for attempt in range(MAX_RETRIES):
        try:
            bars = fetch(ticker)
            if len(bars) < 60:
                raise MarketError(f"Historial insuficiente para {ticker}")
            with _cache_lock:
                _cache[ticker] = (time.monotonic(), bars)
            return bars
        except Exception as exc:  # noqa: BLE001 — reintenta ante cualquier fallo
            last_err = exc
            wait = 2 ** attempt
            logger.warning("Fallo al obtener %s (intento %d/%d): %s",
                           ticker, attempt + 1, MAX_RETRIES, exc)
            if attempt < MAX_RETRIES - 1:
                time.sleep(wait)
    raise MarketError(str(last_err))


def clear_cache() -> None:
    with _cache_lock:
        _cache.clear()


def closed_bars(bars, now=None):
    """Acciones USA: excluir sesión actual hasta las 17:00 de Nueva York.

    Margen conservador de una hora tras el cierre regular; cierres anticipados
    se confirman también a las 17:00. No sintetiza barras en días sin sesión.
    """
    from datetime import datetime
    from zoneinfo import ZoneInfo
    now = now or datetime.now(ZoneInfo("America/New_York"))
    now = now.astimezone(ZoneInfo("America/New_York"))
    return [b for b in bars if datetime.fromtimestamp(b.t, ZoneInfo("UTC")).date() < now.date()
            or (datetime.fromtimestamp(b.t, ZoneInfo("UTC")).date() == now.date() and now.hour >= 17)]
