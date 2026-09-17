"""Tests de la API: auth, watchlist CRUD, settings, health."""
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app import market
from conftest import make_bars, trend_series

HEADERS = {"X-Auth-Token": "test-token"}


@pytest.fixture
def client(tmp_db):
    from app.main import app
    market.clear_cache()
    # TestClient SIN context manager: no ejecuta el lifespan, así el
    # scheduler no arranca ni consulta datos reales durante los tests
    yield TestClient(app)


def fake_bars():
    return make_bars(trend_series(250, 50, 100))


def test_health_sin_token(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_watchlist_requiere_token(client):
    assert client.get("/api/watchlist").status_code == 401
    assert client.get("/api/watchlist",
                      headers={"X-Auth-Token": "malo"}).status_code == 401


def test_watchlist_semilla(client):
    with patch.object(market, "_fetch_yfinance", return_value=fake_bars()):
        r = client.get("/api/watchlist", headers=HEADERS)
    assert r.status_code == 200
    data = r.json()
    tickers = [t["ticker"] for t in data["tickers"]]
    assert set(tickers) == {"QQQ", "META", "GOOGL", "AAPL", "MSFT", "AMD"}
    assert data["ma_type"] == "ema"
    first = data["tickers"][0]
    assert first["regime"] in ("golden", "death")
    assert first["price"] is not None


def test_agregar_y_eliminar_ticker(client):
    with patch.object(market, "_fetch_yfinance", return_value=fake_bars()):
        r = client.post("/api/watchlist/NVDA", headers=HEADERS)
        assert r.status_code == 201
        assert r.json()["ticker"] == "NVDA"
        # duplicado
        assert client.post("/api/watchlist/NVDA", headers=HEADERS).status_code == 409
    assert client.delete("/api/watchlist/NVDA", headers=HEADERS).status_code == 204
    assert client.delete("/api/watchlist/NVDA", headers=HEADERS).status_code == 404


def test_agregar_ticker_invalido(client):
    assert client.post("/api/watchlist/no!valido", headers=HEADERS).status_code == 422


def test_agregar_ticker_sin_datos(client, monkeypatch):
    monkeypatch.setattr(market.time, "sleep", lambda s: None)
    with patch.object(market, "_fetch_yfinance",
                      side_effect=ConnectionError("sin datos")):
        assert client.post("/api/watchlist/XXXX", headers=HEADERS).status_code == 404


def test_grupos_crud(client):
    assert client.get("/api/watchlist/groups", headers=HEADERS).json() == {"groups": []}
    r = client.post("/api/watchlist/groups", json={"name": "FANG+2"}, headers=HEADERS)
    assert r.status_code == 201
    assert r.json() == {"groups": ["FANG+2"]}
    # duplicado
    assert client.post("/api/watchlist/groups", json={"name": "FANG+2"}, headers=HEADERS).status_code == 409
    r = client.post("/api/watchlist/groups", json={"name": "Cripto"}, headers=HEADERS)
    assert r.json() == {"groups": ["FANG+2", "Cripto"]}
    # reordenar
    r = client.post("/api/watchlist/groups/Cripto/move", json={"direction": "up"}, headers=HEADERS)
    assert r.json() == {"groups": ["Cripto", "FANG+2"]}
    # renombrar
    r = client.put("/api/watchlist/groups/Cripto", json={"name": "Crypto"}, headers=HEADERS)
    assert r.json() == {"groups": ["Crypto", "FANG+2"]}
    # eliminar
    r = client.delete("/api/watchlist/groups/Crypto", headers=HEADERS)
    assert r.json() == {"groups": ["FANG+2"]}
    assert client.delete("/api/watchlist/groups/No-existe", headers=HEADERS).status_code == 404


def test_asignar_ticker_a_grupo(client):
    with patch.object(market, "_fetch_yfinance", return_value=fake_bars()):
        client.post("/api/watchlist/groups", json={"name": "FANG+2"}, headers=HEADERS)
        r = client.put("/api/watchlist/AAPL/group", json={"group": "FANG+2"}, headers=HEADERS)
        assert r.status_code == 200
        assert r.json()["group"] == "FANG+2"
        r = client.get("/api/watchlist", headers=HEADERS)
        aapl = next(t for t in r.json()["tickers"] if t["ticker"] == "AAPL")
        assert aapl["group"] == "FANG+2"
        # grupo inexistente
        assert client.put("/api/watchlist/AAPL/group", json={"group": "No existe"},
                          headers=HEADERS).status_code == 404
        # volver a sin grupo
        r = client.put("/api/watchlist/AAPL/group", json={"group": None}, headers=HEADERS)
        assert r.json()["group"] is None


def test_ohlc(client):
    with patch.object(market, "_fetch_yfinance", return_value=fake_bars()):
        r = client.get("/api/quotes/QQQ/ohlc", headers=HEADERS)
    assert r.status_code == 200
    data = r.json()
    assert len(data["bars"]) == 250
    assert len(data["ma_fast"]) == 250
    assert "crosses" in data


def test_settings_get_put(client):
    r = client.get("/api/settings", headers=HEADERS)
    assert r.json() == {"ma_type": "ema", "fast_len": 50, "slow_len": 200}
    r = client.put("/api/settings", json={"ma_type": "sma"}, headers=HEADERS)
    assert r.json()["ma_type"] == "sma"
    assert client.put("/api/settings", json={"ma_type": "otro"},
                      headers=HEADERS).status_code == 422


def test_push_subscribe(client):
    sub = {"endpoint": "https://push.example.com/abc",
           "keys": {"p256dh": "clave", "auth": "auth"}}
    assert client.post("/api/push/subscribe", json=sub, headers=HEADERS).status_code == 201
    # sin claves -> 422
    assert client.post("/api/push/subscribe",
                       json={"endpoint": "x", "keys": {}},
                       headers=HEADERS).status_code == 422


def test_push_test_sin_vapid(client):
    assert client.post("/api/push/test", headers=HEADERS).status_code == 503


def test_settings_invalid_update_is_atomic(client):
    before = client.get("/api/settings", headers=HEADERS).json()
    response = client.put("/api/settings", headers=HEADERS,
                          json={"ma_type": "sma", "fast_len": 1})
    assert response.status_code == 422
    assert client.get("/api/settings", headers=HEADERS).json() == before


def test_settings_reject_inverted_periods(client):
    assert client.put("/api/settings", headers=HEADERS,
                      json={"fast_len": 200, "slow_len": 50}).status_code == 422


def test_settings_reset_alert_baseline(client, tmp_db):
    tmp_db.update_regime("QQQ", "golden", "2026-01-01")
    assert client.put("/api/settings", headers=HEADERS,
                      json={"ma_type": "sma"}).status_code == 200
    assert all(row["current_regime"] is None for row in tmp_db.get_watchlist())


def test_manual_mode_never_starts_scheduler(monkeypatch):
    from app import scheduler
    from types import SimpleNamespace
    monkeypatch.setattr(scheduler, "get_settings", lambda: SimpleNamespace(scan_interval_min=0))
    with patch.object(scheduler, "BackgroundScheduler") as factory:
        scheduler.start()
        factory.assert_not_called()


def test_radar_independent_of_cross_settings(client):
    with patch.object(market, "get_bars", return_value=fake_bars()):
        result = client.get("/api/radar200?ma_type=sma", headers=HEADERS)
    assert result.status_code == 200
    assert result.json()["period"] == 200
    assert len(result.json()["items"]) == 6
    assert client.get("/api/settings", headers=HEADERS).json()["ma_type"] == "ema"
    assert client.get("/api/radar200?ma_type=invalid", headers=HEADERS).status_code == 422
    assert client.get("/api/radar200").status_code == 401


def test_radar_single_ticker_includes_group(client):
    # El detalle de un ticker (?ticker=) debe traer el mismo campo "group"
    # que ya trae cada fila del modo lista, para el mismo ticker.
    client.post("/api/watchlist/groups", json={"name": "FANGS"}, headers=HEADERS)
    with patch.object(market, "get_bars", return_value=fake_bars()):
        client.put("/api/watchlist/QQQ/group", json={"group": "FANGS"}, headers=HEADERS)
        result = client.get("/api/radar200?ticker=QQQ", headers=HEADERS)
    assert result.status_code == 200
    assert result.json()["item"]["group"] == "FANGS"


def test_fundamentals_endpoint_merges_technical_semaphore(client):
    from app import fundamentals

    fake_analysis = {
        "ticker": "AAPL", "error": None, "is_fund": False, "sector": "Technology",
        "semaphores": {
            "health": {"level": "green", "label": "Saludable", "detail": "", "score": 8},
            "analyst_consensus": {"level": "green", "label": "Comprar", "analysts": 10, "score": 8, "breakdown": None},
            "target_price": {"level": "green", "label": "+10%", "upside_pct": 0.1, "score": 7},
        },
        "blocks": [],
    }
    with patch.object(fundamentals, "analyze", return_value=fake_analysis), \
         patch.object(market, "get_bars", return_value=fake_bars()):
        result = client.get("/api/fundamentals/AAPL", headers=HEADERS)
    assert result.status_code == 200
    tech = result.json()["semaphores"]["technical"]
    assert tech["level"] in ("strong_buy", "buy", "neutral", "sell", "strong_sell")
    assert tech["color"] in ("green", "yellow", "red")
    assert set(tech["moving_averages"]) >= {"level", "color", "label", "score"}
    assert set(tech["oscillators"]) >= {"level", "color", "label", "score"}


def test_fundamentals_endpoint_handles_missing_bars(client):
    from app import fundamentals

    fake_analysis = {"ticker": "XXXX", "error": None, "is_fund": False, "sector": None,
                     "semaphores": {"health": {}, "analyst_consensus": {}, "target_price": {}}, "blocks": []}
    with patch.object(fundamentals, "analyze", return_value=fake_analysis), \
         patch.object(market, "get_bars", side_effect=market.MarketError("sin datos")):
        result = client.get("/api/fundamentals/XXXX", headers=HEADERS)
    assert result.status_code == 200
    assert result.json()["semaphores"]["technical"]["level"] == "none"
