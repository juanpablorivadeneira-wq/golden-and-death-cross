"""Escaneo periódico de la watchlist con APScheduler.

En cada pasada se calcula el régimen actual de cada ticker y se compara con
el guardado en la base; si cambió, se persiste y se envía push.
"""
import logging
from datetime import datetime, timezone

from apscheduler.schedulers.background import BackgroundScheduler

from . import db, engine, market, push
from .config import get_settings

logger = logging.getLogger(__name__)

_scheduler: BackgroundScheduler | None = None
_last_scan: str | None = None


def last_scan() -> str | None:
    return _last_scan


def _market_hours_now() -> bool:
    """Aproximación simple: lunes-viernes, 13:00-22:00 UTC (9-17 ET aprox.)."""
    now = datetime.now(timezone.utc)
    return now.weekday() < 5 and 13 <= now.hour < 22


def scan_watchlist() -> dict:
    """Una pasada completa. Devuelve resumen (para logs y pruebas)."""
    global _last_scan
    settings = get_settings()
    if settings.scan_market_hours_only and not _market_hours_now():
        logger.info("Fuera de horario de mercado; escaneo omitido")
        return {"skipped": True}

    ma_type, fast_len, slow_len = db.get_engine_settings()
    summary = {"scanned": 0, "errors": 0, "crosses": 0}

    for row in db.get_watchlist():
        ticker = row["ticker"]
        try:
            bars = market.get_bars(ticker)
            metrics = engine.analyze(ticker, bars, ma_type, fast_len, slow_len)
            if metrics.error:
                summary["errors"] += 1
                logger.warning("%s: %s", ticker, metrics.error)
                continue
            summary["scanned"] += 1

            prev_regime = row["current_regime"]
            if prev_regime and prev_regime != metrics.regime:
                logger.info("CRUCE DETECTADO %s: %s -> %s", ticker, prev_regime, metrics.regime)
                summary["crosses"] += 1
                push.notify_cross(ticker, metrics.regime, metrics.ma_fast,
                                  metrics.ma_slow, metrics.price,
                                  ma_type, fast_len, slow_len)
            db.update_regime(ticker, metrics.regime, metrics.cross_date)
        except market.MarketError as exc:
            summary["errors"] += 1
            logger.warning("%s: error de datos: %s", ticker, exc)
        except Exception:  # noqa: BLE001 — el escaneo nunca debe morir
            summary["errors"] += 1
            logger.exception("%s: error inesperado en el escaneo", ticker)

    _last_scan = datetime.now(timezone.utc).isoformat()
    logger.info("Escaneo completo: %s", summary)
    return summary


def start() -> None:
    global _scheduler
    settings = get_settings()
    _scheduler = BackgroundScheduler(timezone="UTC")
    _scheduler.add_job(scan_watchlist, "interval",
                       minutes=settings.scan_interval_min,
                       id="scan", max_instances=1, coalesce=True,
                       next_run_time=datetime.now(timezone.utc))
    _scheduler.start()
    logger.info("Scheduler iniciado: escaneo cada %d min", settings.scan_interval_min)


def stop() -> None:
    if _scheduler:
        _scheduler.shutdown(wait=False)
