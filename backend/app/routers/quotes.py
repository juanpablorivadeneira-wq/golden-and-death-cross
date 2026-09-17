"""Series OHLC + medias + marcadores de cruce para el gráfico, y settings."""
from fastapi import APIRouter, Depends, HTTPException

from .. import db, engine, market
from ..auth import require_token
from ..models import OhlcResponse, SettingsPayload

router = APIRouter(prefix="/api", tags=["quotes"],
                   dependencies=[Depends(require_token)])


@router.get("/quotes/{ticker}/ohlc", response_model=OhlcResponse)
def get_ohlc(ticker: str) -> OhlcResponse:
    ticker = ticker.strip().upper()
    ma_type, fast_len, slow_len = db.get_engine_settings()
    try:
        bars = market.get_bars(ticker)
    except market.MarketError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    fast, slow, markers = engine.cross_markers(bars, ma_type, fast_len, slow_len)
    return OhlcResponse(ticker=ticker, bars=bars, ma_fast=fast,
                        ma_slow=slow, crosses=markers)


@router.get("/settings")
def get_app_settings() -> dict:
    ma_type, fast_len, slow_len = db.get_engine_settings()
    return {"ma_type": ma_type, "fast_len": fast_len, "slow_len": slow_len}


@router.put("/settings")
def update_app_settings(payload: SettingsPayload) -> dict:
    try:
        db.update_engine_settings(payload.ma_type, payload.fast_len, payload.slow_len)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return get_app_settings()


@router.get("/alerts")
def alerts():
    from .. import push, scheduler
    return {"items": db.get_alerts(), "last_scan": scheduler.last_scan(),
            "push_configured": push.push_configured(), "subscriptions": len(db.get_subscriptions())}


@router.post("/scan")
def scan_now():
    from .. import scheduler
    return scheduler.scan_watchlist()


@router.get("/radar200")
def radar_200(ma_type: str = "sma", refresh: bool = False, ticker: str | None = None):
    from concurrent.futures import ThreadPoolExecutor
    from .. import radar200
    if ma_type not in ("sma", "ema"):
        raise HTTPException(status_code=422, detail="Media inválida")

    def analyze_one(t: str) -> dict:
        try:
            return radar200.analyze(t, market.get_bars(t, force=refresh), ma_type)
        except market.MarketError as exc:
            return {"ticker": t, "error": str(exc)}

    if ticker:
        ticker = ticker.strip().upper()
        item = analyze_one(ticker)
        # Mismo campo "group" que ya lleva cada fila del modo lista -- si no,
        # el detalle de un ticker (usado por el gráfico) queda con una forma
        # distinta a la de la lista para el mismo ticker.
        row = next((r for r in db.get_watchlist() if r["ticker"] == ticker), None)
        item["group"] = row["group_name"] if row else None
        return {"ma_type": ma_type, "period": 200,
                "ma_trend_lookback": radar200.TREND_LOOKBACK, "item": item}

    # Modo lista: sin bars/series (esos solo se piden para el ticker seleccionado,
    # vía ?ticker=, evitando serializar 5 años de historia por cada fila de la lista).
    def summary(row) -> dict:
        result = analyze_one(row["ticker"])
        result = {k: v for k, v in result.items() if k not in ("bars", "series")}
        result["group"] = row["group_name"]
        return result

    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(summary, db.get_watchlist()))
    return {"ma_type": ma_type, "period": 200,
            "ma_trend_lookback": radar200.TREND_LOOKBACK, "items": results}


@router.get("/fundamentals/{ticker}")
def get_fundamentals(ticker: str, refresh: bool = False) -> dict:
    from concurrent.futures import ThreadPoolExecutor
    from .. import fundamentals, technical
    ticker = ticker.strip().upper()
    # fundamentals.analyze (yfinance .info/recomendaciones/estados financieros)
    # y market.get_bars (5 años de OHLC diario) no dependen entre sí -- en
    # paralelo, el tiempo de espera es el máximo de los dos, no la suma.
    with ThreadPoolExecutor(max_workers=2) as pool:
        fut_result = pool.submit(fundamentals.analyze, ticker, force=refresh)
        fut_bars = pool.submit(market.get_bars, ticker, force=refresh)
        result = fut_result.result()
        if result.get("error"):
            return result
        # A diferencia de los semáforos fundamentales (que no aplican a ETFs), el
        # medidor técnico se calcula solo con precio -- funciona igual para
        # cualquier ticker con historial, ETFs incluidos.
        try:
            bars = fut_bars.result()
            tech = technical.analyze(bars)
            # El semáforo usa el resumen combinado (medias + osciladores) como
            # nivel/score principal, y guarda el desglose de cada grupo para
            # el detalle -- mismo patrón que "breakdown" en consenso de analistas.
            result["semaphores"]["technical"] = {
                **tech["summary"],
                "moving_averages": tech["moving_averages"],
                "oscillators": tech["oscillators"],
            }
        except market.MarketError:
            result["semaphores"]["technical"] = {
                "level": "none", "label": "Sin datos", "score": None, "buy": 0, "sell": 0, "neutral": 0,
                "moving_averages": None, "oscillators": None}
    return result
