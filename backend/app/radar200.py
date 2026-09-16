"""Distancia del precio a una media fija de 200 sesiones."""
from datetime import datetime, timezone
from . import engine

TREND_LOOKBACK = 10  # sesiones hacia atrás para juzgar si la media sube o baja


def _ma_trend(series: list, lookback: int = TREND_LOOKBACK) -> str | None:
    """'up'/'down'/'flat' comparando la media actual contra hace `lookback` sesiones.

    El único llamador (analyze) ya exige len(bars) >= 200 > lookback, así que esta
    guarda no se activa hoy; se mantiene porque `series[-1 - lookback]` sería un
    IndexError con una serie más corta que lookback+1 si esta función se reutiliza.
    """
    if len(series) <= lookback:
        return None
    current, prev = series[-1], series[-1 - lookback]
    if prev is not None and prev <= 0:
        return None
    return engine.trend_direction(current, prev)


def analyze(ticker, bars, ma_type="sma"):
    if len(bars) < 200:
        return {"ticker": ticker, "error": "Se necesitan al menos 200 sesiones"}
    series = (engine.ema_series if ma_type == "ema" else engine.sma_series)([b.c for b in bars], 200)
    average = series[-1]
    if not average or average <= 0:
        return {"ticker": ticker, "error": "Media 200 no disponible"}
    distance = (bars[-1].c / average - 1) * 100
    return {"ticker": ticker, "price": bars[-1].c, "average": average,
            "distance_pct": distance, "ma_trend": _ma_trend(series),
            "bar_date": datetime.fromtimestamp(bars[-1].t, timezone.utc).strftime("%Y-%m-%d"),
            "bars": [b.model_dump() for b in bars], "series": series, "error": None}
