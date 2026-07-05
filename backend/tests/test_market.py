"""Tests de market.py con mocks: caché TTL y reintentos."""
from unittest.mock import patch

import pytest

from app import market
from conftest import make_bars, trend_series


@pytest.fixture(autouse=True)
def clean_cache():
    market.clear_cache()
    yield
    market.clear_cache()


def fake_bars():
    return make_bars(trend_series(250, 50, 100))


def test_cache_evita_segunda_llamada():
    with patch.object(market, "_fetch_yfinance", return_value=fake_bars()) as mock:
        market.get_bars("QQQ")
        market.get_bars("QQQ")
        assert mock.call_count == 1


def test_force_ignora_cache():
    with patch.object(market, "_fetch_yfinance", return_value=fake_bars()) as mock:
        market.get_bars("QQQ")
        market.get_bars("QQQ", force=True)
        assert mock.call_count == 2


def test_reintentos_y_exito(monkeypatch):
    monkeypatch.setattr(market.time, "sleep", lambda s: None)
    calls = {"n": 0}

    def flaky(ticker):
        calls["n"] += 1
        if calls["n"] < 3:
            raise ConnectionError("timeout")
        return fake_bars()

    with patch.object(market, "_fetch_yfinance", side_effect=flaky):
        bars = market.get_bars("META")
        assert len(bars) == 250
        assert calls["n"] == 3


def test_agota_reintentos(monkeypatch):
    monkeypatch.setattr(market.time, "sleep", lambda s: None)
    with patch.object(market, "_fetch_yfinance", side_effect=ConnectionError("caído")):
        with pytest.raises(market.MarketError):
            market.get_bars("AAPL")


def test_historial_corto_es_error(monkeypatch):
    monkeypatch.setattr(market.time, "sleep", lambda s: None)
    with patch.object(market, "_fetch_yfinance",
                      return_value=make_bars([100.0] * 10)):
        with pytest.raises(market.MarketError):
            market.get_bars("NUEVO")
