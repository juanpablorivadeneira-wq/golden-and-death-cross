"""Medidor técnico simplificado, inspirado en el "Technical Rating" de
TradingView -- NO es una réplica exacta (esa combina ~26 indicadores
propietarios). Acá promediamos dos grupos de señales calculadas directamente
de las barras diarias que ya usa el motor de cruces, sin ningún dato ni
proveedor adicional:

- Medias móviles: SMA y EMA en 6 períodos (10/20/30/50/100/200) -- compra si
  el precio está por encima, venta si está por debajo.
- Osciladores: RSI(14), MACD(12,26,9), Estocástico(14,3,3) y CCI(20), cada
  uno con su regla de sobrecompra/sobreventa estándar.

El resultado es un promedio simple (compras - ventas) / total de cada grupo
y del conjunto, mapeado a 5 niveles (venta fuerte .. compra fuerte). Es una
aproximación honesta, no un indicador certificado -- documentado así en la
propia página.
"""
from .engine import ema_series, ratio_to_score10, sma_series
from .models import Bar

MA_PERIODS = [10, 20, 30, 50, 100, 200]
MIN_BARS = 210  # 200 (MA más larga) + margen para que no sea el primer valor válido


def _rolling_extreme(values: list[float], period: int, pick) -> list[float | None]:
    """`pick` = max o min. None hasta tener `period` valores."""
    out: list[float | None] = [None] * len(values)
    for i in range(len(values)):
        if i < period - 1:
            continue
        out[i] = pick(values[i - period + 1:i + 1])
    return out


def _rsi(closes: list[float], period: int = 14) -> float | None:
    if len(closes) < period + 1:
        return None
    gains = [max(closes[i] - closes[i - 1], 0.0) for i in range(1, len(closes))]
    losses = [max(closes[i - 1] - closes[i], 0.0) for i in range(1, len(closes))]
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    for i in range(period, len(gains)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def _macd(closes: list[float]) -> tuple[float, float] | None:
    ema12 = ema_series(closes, 12)
    ema26 = ema_series(closes, 26)
    macd_line = [a - b for a, b in zip(ema12, ema26) if a is not None and b is not None]
    if len(macd_line) < 9:
        return None
    signal_line = ema_series(macd_line, 9)
    if signal_line[-1] is None:
        return None
    return macd_line[-1], signal_line[-1]


def _stochastic(bars: list[Bar], k_period: int = 14, smooth: int = 3, d_period: int = 3) -> tuple[float, float] | None:
    highs = [b.h for b in bars]
    lows = [b.l for b in bars]
    closes = [b.c for b in bars]
    highest = _rolling_extreme(highs, k_period, max)
    lowest = _rolling_extreme(lows, k_period, min)
    raw_k: list[float | None] = [None] * len(closes)
    for i in range(len(closes)):
        if highest[i] is None or lowest[i] is None:
            continue
        span = highest[i] - lowest[i]
        raw_k[i] = 50.0 if span == 0 else (closes[i] - lowest[i]) / span * 100
    valid_k = [v for v in raw_k if v is not None]
    if len(valid_k) < smooth + d_period:
        return None
    k_smoothed = sma_series(valid_k, smooth)
    k_valid = [v for v in k_smoothed if v is not None]
    if len(k_valid) < d_period:
        return None
    d_smoothed = sma_series(k_valid, d_period)
    if d_smoothed[-1] is None:
        return None
    return k_valid[-1], d_smoothed[-1]


def _cci(bars: list[Bar], period: int = 20) -> float | None:
    typical = [(b.h + b.l + b.c) / 3 for b in bars]
    if len(typical) < period:
        return None
    window = typical[-period:]
    mean = sum(window) / period
    mean_dev = sum(abs(x - mean) for x in window) / period
    if mean_dev == 0:
        return None
    return (typical[-1] - mean) / (0.015 * mean_dev)


def _ma_signals(closes: list[float]) -> list[str]:
    signals = []
    last = closes[-1]
    for period in MA_PERIODS:
        for series_fn in (sma_series, ema_series):
            series = series_fn(closes, period)
            ma = series[-1]
            if ma is None:
                continue
            signals.append("buy" if last > ma else "sell" if last < ma else "neutral")
    return signals


def _oscillator_signals(bars: list[Bar], closes: list[float]) -> list[str]:
    signals = []
    rsi = _rsi(closes)
    if rsi is not None:
        signals.append("buy" if rsi < 30 else "sell" if rsi > 70 else "neutral")
    macd = _macd(closes)
    if macd is not None:
        macd_line, signal_line = macd
        signals.append("buy" if macd_line > signal_line else "sell" if macd_line < signal_line else "neutral")
    stoch = _stochastic(bars)
    if stoch is not None:
        k, d = stoch
        if k < 20 and k > d:
            signals.append("buy")
        elif k > 80 and k < d:
            signals.append("sell")
        else:
            signals.append("neutral")
    cci = _cci(bars)
    if cci is not None:
        signals.append("buy" if cci < -100 else "sell" if cci > 100 else "neutral")
    return signals


# El nivel de 5 vías (venta fuerte..compra fuerte) es específico de este
# medidor; `color` lo reduce a los mismos green/yellow/red/none que ya usan
# los otros 3 semáforos, para que el frontend no tenga que traducirlo con su
# propia tabla -- una sola fuente de verdad para "qué color es este nivel".
_LEVEL_COLOR = {
    "strong_buy": "green", "buy": "green", "neutral": "yellow",
    "sell": "red", "strong_sell": "red", "none": "none",
}


def _score_and_level(signals: list[str]) -> dict:
    if not signals:
        return {"level": "none", "color": "none", "label": "Sin datos", "score": None,
                "buy": 0, "sell": 0, "neutral": 0}
    buy = signals.count("buy")
    sell = signals.count("sell")
    neutral = signals.count("neutral")
    ratio = (buy - sell) / len(signals)
    score_10 = ratio_to_score10(ratio)
    if ratio >= 0.5:
        level, label = "strong_buy", "Compra fuerte"
    elif ratio >= 0.1:
        level, label = "buy", "Compra"
    elif ratio > -0.1:
        level, label = "neutral", "Neutral"
    elif ratio > -0.5:
        level, label = "sell", "Venta"
    else:
        level, label = "strong_sell", "Venta fuerte"
    return {"level": level, "color": _LEVEL_COLOR[level], "label": label, "score": score_10,
            "buy": buy, "sell": sell, "neutral": neutral}


def analyze(bars: list[Bar]) -> dict:
    closes = [b.c for b in bars]
    if len(closes) < MIN_BARS:
        empty = {"level": "none", "label": "Sin datos", "score": None, "buy": 0, "sell": 0, "neutral": 0}
        return {"moving_averages": empty, "oscillators": empty, "summary": empty}
    ma_signals = _ma_signals(closes)
    osc_signals = _oscillator_signals(bars, closes)
    return {
        "moving_averages": _score_and_level(ma_signals),
        "oscillators": _score_and_level(osc_signals),
        "summary": _score_and_level(ma_signals + osc_signals),
    }
