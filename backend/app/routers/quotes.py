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
    if payload.ma_type is not None:
        if payload.ma_type not in ("ema", "sma"):
            raise HTTPException(status_code=422, detail="ma_type debe ser ema o sma")
        db.set_setting("ma_type", payload.ma_type)
    if payload.fast_len is not None:
        if not 2 <= payload.fast_len <= 500:
            raise HTTPException(status_code=422, detail="fast_len fuera de rango")
        db.set_setting("fast_len", str(payload.fast_len))
    if payload.slow_len is not None:
        if not 2 <= payload.slow_len <= 500:
            raise HTTPException(status_code=422, detail="slow_len fuera de rango")
        db.set_setting("slow_len", str(payload.slow_len))
    return get_app_settings()
