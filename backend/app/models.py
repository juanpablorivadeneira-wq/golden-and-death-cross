"""Modelos de dominio (pydantic) compartidos entre routers y motor."""
from typing import Optional

from pydantic import BaseModel


class Bar(BaseModel):
    """Barra OHLC diaria; t en segundos Unix (UTC, medianoche)."""
    t: int
    o: float
    h: float
    l: float
    c: float


class TickerMetrics(BaseModel):
    """Resultado del análisis de un ticker (equivale al analyze() del prototipo)."""
    ticker: str
    price: Optional[float] = None
    ma_fast: Optional[float] = None
    ma_slow: Optional[float] = None
    regime: Optional[str] = None            # "golden" | "death"
    cross_date: Optional[str] = None        # ISO yyyy-mm-dd del último cruce
    sessions_since_cross: Optional[int] = None
    fresh_cross: bool = False               # el cruce ocurrió en la última barra
    gap_pct: Optional[float] = None         # (fast-slow)/slow*100
    converging: Optional[bool] = None
    est_sessions_to_cross: Optional[float] = None  # null si divergen o >250
    error: Optional[str] = None


class WatchlistResponse(BaseModel):
    ma_type: str
    fast_len: int
    slow_len: int
    tickers: list[TickerMetrics]


class CrossMarker(BaseModel):
    t: int
    type: str  # "golden" | "death"


class OhlcResponse(BaseModel):
    ticker: str
    bars: list[Bar]
    ma_fast: list[Optional[float]]
    ma_slow: list[Optional[float]]
    crosses: list[CrossMarker]


class SettingsPayload(BaseModel):
    ma_type: Optional[str] = None   # "ema" | "sma"
    fast_len: Optional[int] = None
    slow_len: Optional[int] = None


class PushSubscription(BaseModel):
    endpoint: str
    keys: dict


class HealthResponse(BaseModel):
    status: str
    last_scan: Optional[str] = None
    data_source: str
    scan_interval_min: int
