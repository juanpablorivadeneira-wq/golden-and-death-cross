"""Motor de cálculo: medias móviles, detección de cruces y métricas.

Portado exactamente del prototipo cross_monitor_v3.html (JavaScript).
La EMA usa semilla SMA de los primeros `length` valores, igual que el JS.
"""
from datetime import datetime, timezone
from typing import Optional

from .models import Bar, CrossMarker, TickerMetrics


def sma_series(closes: list[float], length: int) -> list[Optional[float]]:
    """SMA rolling; None hasta tener `length` valores."""
    out: list[Optional[float]] = [None] * len(closes)
    total = 0.0
    for i, c in enumerate(closes):
        total += c
        if i >= length:
            total -= closes[i - length]
        if i >= length - 1:
            out[i] = total / length
    return out


def ema_series(closes: list[float], length: int) -> list[Optional[float]]:
    """EMA con semilla SMA de los primeros `length` valores (idéntica al JS)."""
    out: list[Optional[float]] = [None] * len(closes)
    k = 2 / (length + 1)
    ema: Optional[float] = None
    seed = 0.0
    for i, c in enumerate(closes):
        if i < length - 1:
            seed += c
            continue
        if i == length - 1:
            ema = (seed + c) / length
            out[i] = ema
            continue
        ema = c * k + ema * (1 - k)
        out[i] = ema
    return out


def compute_mas(closes: list[float], ma_type: str, fast_len: int, slow_len: int):
    fn = ema_series if ma_type == "ema" else sma_series
    return fn(closes, fast_len), fn(closes, slow_len)


def find_crosses(fast: list[Optional[float]], slow: list[Optional[float]],
                 slow_len: int) -> list[dict]:
    """Cambio de signo de fast-slow entre barras consecutivas, ignorando MAs nulas."""
    crosses = []
    for i in range(slow_len, len(fast)):
        if fast[i] is None or slow[i] is None or fast[i - 1] is None or slow[i - 1] is None:
            continue
        now_above = fast[i] > slow[i]
        prev_above = fast[i - 1] > slow[i - 1]
        if now_above != prev_above:
            crosses.append({"idx": i, "type": "golden" if now_above else "death"})
    return crosses


def analyze(ticker: str, bars: list[Bar], ma_type: str,
            fast_len: int, slow_len: int) -> TickerMetrics:
    """Métricas completas de un ticker: régimen, cruce, brecha, convergencia."""
    closes = [b.c for b in bars]
    if len(closes) < slow_len + 10:
        return TickerMetrics(ticker=ticker, error="Historial insuficiente")

    fast, slow = compute_mas(closes, ma_type, fast_len, slow_len)
    n = len(bars) - 1
    if fast[n] is None or slow[n] is None:
        return TickerMetrics(ticker=ticker, error="Medias no disponibles")

    regime = "golden" if fast[n] > slow[n] else "death"
    crosses = find_crosses(fast, slow, slow_len)
    last = crosses[-1] if crosses else None

    gap = fast[n] - slow[n]
    gap_pct = gap / slow[n] * 100

    # Convergencia: pendiente de la brecha en las últimas 5 barras
    converging = None
    est_days = None
    if fast[n - 5] is not None and slow[n - 5] is not None:
        gap_prev = fast[n - 5] - slow[n - 5]
        daily_conv = (gap_prev - gap) / 5
        converging = (gap > 0 and daily_conv > 0) or (gap < 0 and daily_conv < 0)
        if converging and abs(daily_conv) > 1e-9:
            est_days = abs(gap) / abs(daily_conv)
            if est_days > 250:
                est_days = None

    cross_date = None
    if last:
        cross_date = datetime.fromtimestamp(bars[last["idx"]].t, tz=timezone.utc).strftime("%Y-%m-%d")

    return TickerMetrics(
        ticker=ticker,
        price=closes[n],
        ma_fast=fast[n],
        ma_slow=slow[n],
        regime=regime,
        cross_date=cross_date,
        sessions_since_cross=(n - last["idx"]) if last else None,
        fresh_cross=bool(last and last["idx"] == n),
        gap_pct=gap_pct,
        converging=converging,
        est_sessions_to_cross=est_days,
    )


def cross_markers(bars: list[Bar], ma_type: str, fast_len: int, slow_len: int):
    """Series de MAs y marcadores de cruce para el gráfico."""
    closes = [b.c for b in bars]
    fast, slow = compute_mas(closes, ma_type, fast_len, slow_len)
    markers = [CrossMarker(t=bars[c["idx"]].t, type=c["type"])
               for c in find_crosses(fast, slow, slow_len)]
    return fast, slow, markers
