from datetime import datetime, timezone
from unittest.mock import patch
from types import SimpleNamespace
from app import db, scheduler, market, push
from app.models import TickerMetrics
from conftest import make_bars


def metric(regime="golden", date="2026-09-14"):
    return TickerMetrics(ticker="QQQ", regime=regime, cross_date=date, price=100, ma_fast=101, ma_slow=99)


def test_first_scan_baselines_then_new_cross_is_saved_once(tmp_db):
    for row in db.get_watchlist():
        if row["ticker"] != "QQQ": db.remove_ticker(row["ticker"])
    with patch.object(market, "get_bars", return_value=[]), patch.object(push, "deliver_alerts"), patch.object(scheduler.engine, "analyze", return_value=metric()):
        scheduler.scan_watchlist()
        assert db.get_alerts() == []
    with patch.object(market, "get_bars", return_value=[]), patch.object(push, "deliver_alerts"), patch.object(scheduler.engine, "analyze", return_value=metric("death", "2026-09-15")):
        scheduler.scan_watchlist()
        scheduler.scan_watchlist()
        assert len(db.get_alerts()) == 1
        assert db.get_alerts()[0]["regime"] == "death"


def test_configuration_change_does_not_create_alert(tmp_db):
    db.update_regime("QQQ", "death", "2026-09-01")
    db.update_engine_settings("sma")
    with patch.object(market, "get_bars", return_value=[]), patch.object(push, "deliver_alerts"), patch.object(scheduler.engine, "analyze", return_value=metric()):
        scheduler.scan_watchlist()
    assert db.get_alerts() == []


def test_current_session_excluded_before_confirmation():
    bars = make_bars([100])
    bars[0].t = int(datetime(2026,9,15,4,tzinfo=timezone.utc).timestamp())
    assert market.closed_bars(bars, datetime(2026,9,15,20,tzinfo=timezone.utc)) == []
    assert market.closed_bars(bars, datetime(2026,9,15,21,tzinfo=timezone.utc)) == bars


def test_daily_schedule_has_no_interval_polling(monkeypatch):
    monkeypatch.setattr(scheduler, "get_settings", lambda: SimpleNamespace(scan_daily=True))
    with patch.object(scheduler, "BackgroundScheduler") as factory:
        scheduler.start()
        args = factory.return_value.add_job.call_args
        assert args.args[1] == "cron"
        assert args.kwargs["hour"] == 17
        assert args.kwargs["day_of_week"] == "mon-fri"


def test_failed_delivery_retries_without_repeating_success(tmp_db):
    db.save_subscription("https://example.com/push", '{"p256dh":"test","auth":"test"}')
    db.save_alert(metric(), "ema", 50, 200)
    settings = SimpleNamespace(vapid_private_key="test", vapid_claim_email="test@example.com")
    with patch.object(push, "push_configured", return_value=True), patch.object(push, "get_settings", return_value=settings), patch.object(push, "webpush", side_effect=[RuntimeError("offline"), None]) as send:
        push.deliver_alerts()
        push.deliver_alerts()
        push.deliver_alerts()
        assert send.call_count == 2
