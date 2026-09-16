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
def radar_200(ma_type: str = "sma", refresh: bool = False):
    from concurrent.futures import ThreadPoolExecutor
    from .. import radar200
    if ma_type not in ("sma", "ema"):
        raise HTTPException(status_code=422, detail="Media inválida")
    def analyze_ticker(row):
        try:
            return radar200.analyze(row["ticker"], market.get_bars(row["ticker"], force=refresh), ma_type)
        except market.MarketError as exc:
            return {"ticker": row["ticker"], "error": str(exc)}
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(analyze_ticker, db.get_watchlist()))
    return {"ma_type": ma_type, "period": 200, "items": results}
