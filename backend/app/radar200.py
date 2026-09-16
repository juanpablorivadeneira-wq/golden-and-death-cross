"""Distancia del precio a una media fija de 200 sesiones."""
from datetime import datetime, timezone
from . import engine


def analyze(ticker, bars, ma_type="sma"):
    if len(bars) < 200:
        return {"ticker": ticker, "error": "Se necesitan al menos 200 sesiones"}
    series = (engine.ema_series if ma_type == "ema" else engine.sma_series)([b.c for b in bars], 200)
    average = series[-1]
    if not average or average <= 0:
        return {"ticker": ticker, "error": "Media 200 no disponible"}
    distance = (bars[-1].c / average - 1) * 100
    return {"ticker": ticker, "price": bars[-1].c, "average": average,
            "distance_pct": distance, "bar_date": datetime.fromtimestamp(bars[-1].t, timezone.utc).strftime("%Y-%m-%d"),
            "bars": [b.model_dump() for b in bars], "series": series, "error": None}
