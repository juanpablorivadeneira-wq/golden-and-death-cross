"""Diagnóstico técnico según la metodología de David Trullás.

Cuatro módulos independientes calculados sobre las velas OHLCV:

A. Medias SMA 200 (macro), SMA 70 (intermedia) y SMA 6 (gatillo). Largo si la
   200 y la 70 suben y la 70 está sobre la 200; corto si ambas bajan y la 70
   está bajo la 200 (espejo del largo, como en su ejemplo de Netflix). La señal
   la da la posición/cruce de la SMA 6 respecto de la SMA 70.
B. Pivotes (fractales) y divergencias de volumen y de estocástico lento
   (14, 3, 5) entre los dos últimos máximos o mínimos.
C. Proyección del retroceso: 66 % (2/3, Teoría de Dow) y 61,8 % (Fibonacci)
   del impulso entre el extremo absoluto entre P1 y P2 y el propio P2, más
   el 50 % como zona donde el precio también puede frenarse.
D. ATR(14) de Wilder y stop sugerido a N ATR.

Además, un filtro top-down (mercado → sector → activo) en velas diarias y la
fuerza relativa frente al ETF de su sector. Todo es cálculo determinista; no
hay datos de Level-2, así que el order flow se informa como no disponible.
Son heurísticas del proyecto, no una réplica certificada del método.
"""
import logging
import re
import threading
import time
from datetime import datetime, timezone

from .engine import sma_series
from .models import Bar

logger = logging.getLogger(__name__)

SMA_MACRO, SMA_MID, SMA_TRIGGER = 200, 70, 6
SLOPE_LOOKBACK = 5        # velas para medir la pendiente de una media
FRESH_SIGNAL_BARS = 5     # un cruce de la SMA 6 cuenta como "nuevo" durante estas velas
PIVOT_WINDOW = 5          # velas a cada lado para confirmar un fractal
DIVERGENCE_MAX_AGE = 40   # P2 más viejo que esto ya no se considera una alerta activa
STOCH_K, STOCH_SMOOTH, STOCH_D = 14, 3, 5
ATR_PERIOD = 14
DEFAULT_ATR_MULT = 2.0
RS_LOOKBACK = 63          # ~3 meses de sesiones
RS_THRESHOLD_PP = 3.0     # puntos porcentuales para Fuerte / Débil
DOW_RATIO, FIB_RATIO, HALF_RATIO = 0.66, 0.618, 0.5
MIN_BARS = SMA_MACRO + SLOPE_LOOKBACK + 1

SECTOR_ETF = {
    "Technology": "XLK", "Financial Services": "XLF", "Healthcare": "XLV",
    "Consumer Cyclical": "XLY", "Consumer Defensive": "XLP", "Energy": "XLE",
    "Industrials": "XLI", "Basic Materials": "XLB", "Real Estate": "XLRE",
    "Utilities": "XLU", "Communication Services": "XLC",
}
MARKET_BENCHMARK = "SPY"
CRYPTO_BENCHMARK = "BTC-USD"

ASSET_CLASS_LABEL = {"index": "Índice", "equity": "Acción/ETF", "forex": "Forex",
                     "future": "Futuro", "crypto": "Cripto"}


def asset_class(ticker: str) -> str:
    """Clase por convención de símbolos de Yahoo (^GSPC, EURUSD=X, ES=F, BTC-USD)."""
    t = ticker.upper()
    if t.startswith("^"):
        return "index"
    if t.endswith("=X"):
        return "forex"
    if t.endswith("=F"):
        return "future"
    if re.search(r"-(USD|USDT|EUR|BTC)$", t):
        return "crypto"
    return "equity"


def _date(ts: int) -> str:
    return datetime.fromtimestamp(ts, timezone.utc).strftime("%Y-%m-%d")


def _slope(series: list, lookback: int = SLOPE_LOOKBACK) -> float | None:
    if len(series) <= lookback or series[-1] is None or series[-1 - lookback] is None:
        return None
    return series[-1] - series[-1 - lookback]


# ---------------------------------------------------------------- Módulo A
def sma_module(bars: list[Bar]) -> dict:
    closes = [b.c for b in bars]
    s200, s70, s6 = (sma_series(closes, n) for n in (SMA_MACRO, SMA_MID, SMA_TRIGGER))
    slope200, slope70 = _slope(s200), _slope(s70)
    last_cross = None
    for i in range(len(closes) - 1, SMA_MID, -1):
        a0, b0, a1, b1 = s6[i - 1], s70[i - 1], s6[i], s70[i]
        if None in (a0, b0, a1, b1):
            break
        if a0 <= b0 and a1 > b1:
            last_cross = {"type": "up", "index": i}
            break
        if a0 >= b0 and a1 < b1:
            last_cross = {"type": "down", "index": i}
            break
    n = len(closes) - 1
    if last_cross:
        last_cross["bars_ago"] = n - last_cross["index"]
        last_cross["t"] = bars[last_cross["index"]].t
    long_setup = bool(slope200 is not None and slope70 is not None and slope200 > 0
                      and slope70 > 0 and s70[-1] > s200[-1])
    short_setup = bool(slope200 is not None and slope70 is not None and slope200 < 0
                       and slope70 < 0 and s70[-1] < s200[-1])
    trigger_above = s6[-1] > s70[-1]
    fresh = bool(last_cross and last_cross["bars_ago"] < FRESH_SIGNAL_BARS)
    if long_setup and trigger_above:
        signal = "buy"
        note = ("Entrada larga: la SMA 6 acaba de cruzar sobre la SMA 70." if fresh and last_cross["type"] == "up"
                else "Largo vigente: la SMA 6 sigue sobre la SMA 70.")
    elif short_setup and not trigger_above:
        signal = "sell"
        note = ("Entrada corta: la SMA 6 acaba de cruzar bajo la SMA 70." if fresh and last_cross["type"] == "down"
                else "Corto vigente: la SMA 6 sigue bajo la SMA 70.")
    elif long_setup:
        signal = "wait"
        note = "Salida de largos: la SMA 6 cruzó bajo la SMA 70. Esperar un nuevo cruce alcista."
    elif short_setup:
        signal = "wait"
        note = "Salida de cortos: la SMA 6 está sobre la SMA 70. Esperar un nuevo cruce bajista."
    else:
        signal = "wait"
        note = "Medias sin estructura de tendencia: la 200 y la 70 no acompañan en la misma dirección o la 70 está del lado equivocado de la 200."
    return {"signal": signal, "fresh": fresh, "note": note,
            "long_setup": long_setup, "short_setup": short_setup,
            "sma200": s200[-1], "sma70": s70[-1], "sma6": s6[-1],
            "slope200": slope200, "slope70": slope70, "last_cross": last_cross,
            "series": {"sma200": s200, "sma70": s70, "sma6": s6}}


# ---------------------------------------------------------------- Módulo B
def stochastic_slow(bars: list[Bar], k: int = STOCH_K, smooth: int = STOCH_SMOOTH,
                    d: int = STOCH_D) -> tuple[list, list]:
    """%K lento (SMA `smooth` del %K bruto) y %D (SMA `d` del %K lento), alineados a las barras."""
    raw: list = [None] * len(bars)
    for i in range(k - 1, len(bars)):
        window = bars[i - k + 1:i + 1]
        hi, lo = max(b.h for b in window), min(b.l for b in window)
        raw[i] = 50.0 if hi == lo else (bars[i].c - lo) / (hi - lo) * 100

    def rolling(values, n):
        out = [None] * len(values)
        for i in range(len(values)):
            window = values[i - n + 1:i + 1] if i >= n - 1 else []
            if window and None not in window:
                out[i] = sum(window) / n
        return out

    slow_k = rolling(raw, smooth)
    return slow_k, rolling(slow_k, d)


def find_pivots(bars: list[Bar], window: int = PIVOT_WINDOW) -> tuple[list[int], list[int]]:
    """Fractales confirmados: máximo (mínimo) estricto frente a `window` velas por lado."""
    highs, lows = [], []
    for i in range(window, len(bars) - window):
        around = bars[i - window:i] + bars[i + 1:i + window + 1]
        if all(bars[i].h > b.h for b in around):
            highs.append(i)
        if all(bars[i].l < b.l for b in around):
            lows.append(i)
    return highs, lows


def _pivot_volume(bars: list[Bar], i: int) -> float | None:
    """Volumen medio de la vela del pivote y sus vecinas: una sola vela es muy ruidosa."""
    vols = [b.v for b in bars[max(0, i - 1):i + 2]]
    # Un 0 suele ser dato ausente (índices, futuros poco líquidos), no volumen real:
    # promediarlo inventaría una divergencia.
    if any(not v for v in vols):
        return None
    return sum(vols) / len(vols)


def _evaluate_pair(bars, stoch_k, p1, p2, kind) -> dict | None:
    price = (lambda i: bars[i].h) if kind == "high" else (lambda i: bars[i].l)
    v1, v2 = _pivot_volume(bars, p1), _pivot_volume(bars, p2)
    k1, k2 = stoch_k[p1], stoch_k[p2]
    volume_div = stoch_div = False
    if kind == "high" and price(p2) > price(p1):
        direction = "bearish"
        volume_div = v1 is not None and v2 is not None and v2 < v1
        stoch_div = k1 is not None and k2 is not None and k2 < k1
    elif kind == "low" and price(p2) < price(p1):
        direction = "bullish"
        # Nuevo mínimo con menos volumen = menor presión vendedora (agotamiento).
        volume_div = v1 is not None and v2 is not None and v2 < v1
        stoch_div = k1 is not None and k2 is not None and k2 > k1
    else:
        return None
    if not (volume_div or stoch_div):
        return None
    between = bars[p1:p2 + 1]
    if direction == "bearish":
        absolute_idx = p1 + min(range(len(between)), key=lambda j: between[j].l)
        absolute = bars[absolute_idx].l
    else:
        absolute_idx = p1 + max(range(len(between)), key=lambda j: between[j].h)
        absolute = bars[absolute_idx].h
    p2_price = price(p2)
    rango = absolute - p2_price
    return {
        "direction": direction, "volume": volume_div, "stochastic": stoch_div,
        "p1": {"index": p1, "t": bars[p1].t, "price": price(p1), "volume": v1, "stoch": k1},
        "p2": {"index": p2, "t": bars[p2].t, "price": p2_price, "volume": v2, "stoch": k2},
        "absolute": {"index": absolute_idx, "t": bars[absolute_idx].t, "price": absolute},
        "range": rango,
        "target66": p2_price + DOW_RATIO * rango,
        "target618": p2_price + FIB_RATIO * rango,
        "target50": p2_price + HALF_RATIO * rango,
        "bars_ago": len(bars) - 1 - p2,
    }


def divergence_module(bars: list[Bar]) -> dict:
    stoch_k, stoch_d = stochastic_slow(bars)
    highs, lows = find_pivots(bars)
    candidates = []
    if len(highs) >= 2:
        candidates.append(_evaluate_pair(bars, stoch_k, highs[-2], highs[-1], "high"))
    if len(lows) >= 2:
        candidates.append(_evaluate_pair(bars, stoch_k, lows[-2], lows[-1], "low"))
    found = [c for c in candidates if c]
    latest = max(found, key=lambda c: c["p2"]["index"], default=None)
    active = bool(latest and latest["bars_ago"] <= DIVERGENCE_MAX_AGE)
    has_volume = any(b.v for b in bars[-50:])
    return {"active": active, "latest": latest, "has_volume": has_volume,
            "pivot_highs": [bars[i].t for i in highs[-6:]],
            "pivot_lows": [bars[i].t for i in lows[-6:]],
            "stoch_k": stoch_k[-1], "stoch_d": stoch_d[-1],
            "series": {"stoch_k": stoch_k, "stoch_d": stoch_d}}


# ---------------------------------------------------------------- Módulo D
def atr(bars: list[Bar], period: int = ATR_PERIOD) -> float | None:
    if len(bars) <= period:
        return None
    trs = [max(b.h - b.l, abs(b.h - p.c), abs(b.l - p.c)) for p, b in zip(bars, bars[1:])]
    value = sum(trs[:period]) / period
    for tr in trs[period:]:
        value = (value * (period - 1) + tr) / period
    return value


def volatility_module(bars: list[Bar], bias: str, mult: float = DEFAULT_ATR_MULT) -> dict:
    value = atr(bars)
    price = bars[-1].c
    if value is None:
        return {"atr": None, "atr_pct": None, "mult": mult, "stop_long": None, "stop_short": None,
                "stop": None, "side": None, "relative_volume": None}
    side = "short" if bias == "short" else "long"
    stop_long, stop_short = price - mult * value, price + mult * value
    vols = [b.v for b in bars[-21:-1] if b.v]
    rel_vol = bars[-1].v / (sum(vols) / len(vols)) if vols and bars[-1].v else None
    return {"atr": value, "atr_pct": value / price * 100, "mult": mult,
            "stop_long": stop_long, "stop_short": stop_short,
            "stop": stop_short if side == "short" else stop_long, "side": side,
            "relative_volume": rel_vol}


# ------------------------------------------------------ Top-down y sector
def trend_of(bars: list[Bar] | None) -> dict | None:
    """Tendencia macro en diario: precio y pendiente respecto de la SMA 200."""
    if not bars or len(bars) < MIN_BARS:
        return None
    s200 = sma_series([b.c for b in bars], SMA_MACRO)
    slope = _slope(s200)
    price = bars[-1].c
    if slope > 0 and price > s200[-1]:
        trend = "bullish"
    elif slope < 0 and price < s200[-1]:
        trend = "bearish"
    else:
        trend = "neutral"
    return {"trend": trend, "price": price, "sma200": s200[-1], "slope200": slope,
            "distance_pct": (price / s200[-1] - 1) * 100}


def relative_strength(bars: list[Bar], bench: list[Bar] | None, benchmark: str | None) -> dict:
    if not bench or not benchmark:
        return {"label": "none", "value": None, "benchmark": benchmark}
    by_date = {_date(b.t): b.c for b in bench}
    pairs = [(b.c, by_date[_date(b.t)]) for b in bars if _date(b.t) in by_date]
    if len(pairs) <= RS_LOOKBACK:
        return {"label": "none", "value": None, "benchmark": benchmark}
    (a0, b0), (a1, b1) = pairs[-1 - RS_LOOKBACK], pairs[-1]
    value = ((a1 / a0) - (b1 / b0)) * 100
    label = "strong" if value > RS_THRESHOLD_PP else "weak" if value < -RS_THRESHOLD_PP else "neutral"
    return {"label": label, "value": value, "benchmark": benchmark}


_sector_cache: dict[str, tuple[float, str | None]] = {}
_sector_lock = threading.Lock()
SECTOR_TTL_SECONDS = 24 * 3600
SECTOR_RETRY_SECONDS = 600  # un fallo de red no debe fijar "sin sector" todo el día


def sector_of(ticker: str) -> str | None:
    """Sector de Yahoo; se cachea un día porque casi nunca cambia."""
    with _sector_lock:
        hit = _sector_cache.get(ticker)
        if hit and time.monotonic() - hit[0] < (SECTOR_TTL_SECONDS if hit[1] else SECTOR_RETRY_SECONDS):
            return hit[1]
    try:
        import yfinance as yf
        sector = (yf.Ticker(ticker).info or {}).get("sector")
    except Exception as exc:  # noqa: BLE001 — sin sector se compara contra el mercado
        logger.info("Sin sector para %s: %s", ticker, exc)
        sector = None
    with _sector_lock:
        _sector_cache[ticker] = (time.monotonic(), sector)
    return sector


def benchmarks_for(ticker: str) -> dict:
    """ETF de sector (fuerza relativa) y referencia de mercado (top-down)."""
    cls = asset_class(ticker)
    if cls == "crypto":
        return {"market": CRYPTO_BENCHMARK, "sector": CRYPTO_BENCHMARK, "sector_name": "Cripto"}
    if cls == "forex":
        return {"market": None, "sector": None, "sector_name": None}
    if cls in ("index", "future"):
        return {"market": MARKET_BENCHMARK, "sector": MARKET_BENCHMARK, "sector_name": "Mercado"}
    sector = sector_of(ticker)
    etf = SECTOR_ETF.get(sector)
    return {"market": MARKET_BENCHMARK, "sector": etf or MARKET_BENCHMARK,
            "sector_name": sector if etf else "Mercado"}


def top_down(daily: list[Bar], market: dict | None, sector: dict | None, bench: dict) -> dict:
    asset = trend_of(daily)
    levels = [("Mercado", bench["market"], market), ("Sector", bench["sector"], sector),
              ("Activo", None, asset)]
    trends = [lvl[2]["trend"] for lvl in levels if lvl[2]]
    own = asset["trend"] if asset else "neutral"
    # Aprobado si el activo tiene tendencia y ningún nivel superior la contradice.
    opposite = "bearish" if own == "bullish" else "bullish"
    aligned = own != "neutral" and opposite not in trends
    return {"macro_trend": own, "aligned": aligned,
            "levels": [{"level": name, "symbol": sym, **(data or {"trend": None})}
                       for name, sym, data in levels]}


# ------------------------------------------------------------ Orquestador
def analyze(ticker: str, bars: list[Bar], daily: list[Bar] | None = None,
            market: list[Bar] | None = None, sector: list[Bar] | None = None,
            bench: dict | None = None, interval: str = "1d",
            atr_mult: float = DEFAULT_ATR_MULT, include_series: bool = False) -> dict:
    """`bars` son las velas del intervalo elegido; `daily` las diarias del
    mismo activo (para el top-down y la fuerza relativa). En diario coinciden."""
    daily = daily or bars
    bench = bench or {"market": None, "sector": None, "sector_name": None}
    cls = asset_class(ticker)
    base = {"ticker": ticker, "asset_class": cls, "asset_class_label": ASSET_CLASS_LABEL[cls],
            "interval": interval}
    if len(bars) < MIN_BARS:
        return {**base, "error": f"Se necesitan al menos {MIN_BARS} velas"}
    sma = sma_module(bars)
    div = divergence_module(bars)
    td = top_down(daily, trend_of(market), trend_of(sector), bench)
    rs = relative_strength(daily, sector, bench.get("sector"))
    rs["sector_name"] = bench.get("sector_name")
    bias = "long" if sma["long_setup"] else "short" if sma["short_setup"] else (
        "short" if td["macro_trend"] == "bearish" else "long")
    vol = volatility_module(bars, bias, atr_mult)
    latest = div["latest"] if div["active"] else None
    result = {
        **base,
        "price": bars[-1].c, "bar_time": bars[-1].t, "bar_date": _date(bars[-1].t),
        # Contrato resumido de la pestaña (mismos nombres que en el frontend).
        "summary": {
            "ticker": ticker,
            "macroTrend": td["macro_trend"],
            "smaSignal": sma["signal"],
            "divergenceDetected": latest["direction"] if latest else None,
            "targetPrice66": latest["target66"] if latest else None,
            "targetPrice618": latest["target618"] if latest else None,
            "atrStop": vol["stop"],
        },
        "top_down": td,
        "relative_strength": rs,
        "sma": {k: v for k, v in sma.items() if k != "series"},
        "divergence": {k: v for k, v in div.items() if k != "series"},
        "volatility": vol,
        "order_flow": {"available": False,
                       "reason": "Yahoo y Twelve Data no entregan Level-2 ni footprint; "
                                 "se muestra el volumen relativo como aproximación."},
        "error": None,
    }
    if include_series:
        result["bars"] = [b.model_dump() for b in bars]
        result["series"] = {**sma["series"], **div["series"]}
    return result
