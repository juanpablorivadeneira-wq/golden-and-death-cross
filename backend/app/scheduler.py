"""Escaneo periódico de la watchlist con APScheduler.

En cada pasada se calcula el régimen actual de cada ticker y se compara con
el guardado en la base; si cambió, se persiste y se envía push.
"""
import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

from apscheduler.schedulers.background import BackgroundScheduler

from . import db, engine, market, push
from .config import get_settings
from .synchronization import serialized

logger = logging.getLogger(__name__)

_scheduler: BackgroundScheduler | None = None
_last_scan: str | None = None


def last_scan() -> str | None:
    return _last_scan


def _market_hours_now() -> bool:
    """Aproximación simple: lunes-viernes, 13:00-22:00 UTC (9-17 ET aprox.)."""
    now = datetime.now(timezone.utc)
    return now.weekday() < 5 and 13 <= now.hour < 22


@serialized
def scan_watchlist() -> dict:
    """Una pasada completa. Devuelve resumen (para logs y pruebas)."""
    global _last_scan
    settings = get_settings()
    if settings.scan_market_hours_only and not _market_hours_now():
        logger.info("Fuera de horario de mercado; escaneo omitido")
        return {"skipped": True}

    ma_type, fast_len, slow_len = db.get_engine_settings()

    def scan_one(row: dict) -> dict:
        ticker = row["ticker"]
        try:
            bars = market.closed_bars(market.get_bars(ticker, force=True))
            metrics = engine.analyze(ticker, bars, ma_type, fast_len, slow_len)
            if metrics.error:
                logger.warning("%s: %s", ticker, metrics.error)
                return {"scanned": 0, "errors": 1, "crosses": 0}

            prev_regime = row["current_regime"]
            previous_date = row["last_cross_date"]
            new_cross = (metrics.cross_date and prev_regime and
                         ((previous_date and metrics.cross_date > previous_date) or
                          (not previous_date and prev_regime != metrics.regime)))
            crossed = bool(new_cross and db.save_alert(metrics, ma_type, fast_len, slow_len))
            db.update_regime(ticker, metrics.regime, metrics.cross_date)
            return {"scanned": 1, "errors": 0, "crosses": int(crossed)}
        except market.MarketError as exc:
            logger.warning("%s: error de datos: %s", ticker, exc)
            return {"scanned": 0, "errors": 1, "crosses": 0}
        except Exception:  # noqa: BLE001 — el escaneo nunca debe morir
            logger.exception("%s: error inesperado en el escaneo", ticker)
            return {"scanned": 0, "errors": 1, "crosses": 0}

    # Fetches en paralelo: cada ticker ahora trae ~5 años de historia, y hacerlo
    # secuencial haría crecer la duración del escaneo con cada ticker agregado.
    summary = {"scanned": 0, "errors": 0, "crosses": 0}
    with ThreadPoolExecutor(max_workers=6) as pool:
        for partial in pool.map(scan_one, db.get_watchlist()):
            for key in summary:
                summary[key] += partial[key]

    push.deliver_alerts()
    _last_scan = datetime.now(timezone.utc).isoformat()
    logger.info("Escaneo completo: %s", summary)
    return summary


def start() -> None:
    global _scheduler
    settings = get_settings()
    if getattr(settings, "scan_daily", False):
        _scheduler = BackgroundScheduler(timezone="America/New_York")
        _scheduler.add_job(scan_watchlist, "cron", day_of_week="mon-fri", hour=17, minute=0,
                           id="scan", max_instances=1, coalesce=True, misfire_grace_time=3600)
        _scheduler.start()
        logger.info("Revisión diaria: 17:00 America/New_York")
        return
    if settings.scan_interval_min <= 0:
        logger.info("Modo manual: escaneo automático desactivado")
        return
    _scheduler = BackgroundScheduler(timezone="UTC")
    _scheduler.add_job(scan_watchlist, "interval", minutes=settings.scan_interval_min,
                       id="scan", max_instances=1, coalesce=True)
    _scheduler.start()


def stop() -> None:
    if _scheduler:
        _scheduler.shutdown(wait=False)
