"""Tests del diagnóstico David Trullás: medias, divergencias, retrocesos, ATR."""
from unittest.mock import patch

import pytest

from app import trullas
from app.models import Bar
from conftest import DAY, T0, make_bars, trend_series


def bars_from(points, vols=None):
    """Barras con máximo/mínimo = cierre ± 0.5 y volumen opcional por vela."""
    vols = vols or [1000.0] * len(points)
    return [Bar(t=T0 + i * DAY, o=c, h=c + 0.5, l=c - 0.5, c=c, v=v)
            for i, (c, v) in enumerate(zip(points, vols))]


def test_asset_class_por_simbolo():
    assert trullas.asset_class("^GSPC") == "index"
    assert trullas.asset_class("EURUSD=X") == "forex"
    assert trullas.asset_class("ES=F") == "future"
    assert trullas.asset_class("BTC-USD") == "crypto"
    assert trullas.asset_class("AAPL") == "equity"


def test_tendencia_alcista_da_compra():
    sma = trullas.sma_module(make_bars(trend_series(300, 50, 150)))
    assert sma["long_setup"] and sma["signal"] == "buy"
    assert sma["slope200"] > 0 and sma["sma70"] > sma["sma200"]


def test_tendencia_bajista_da_venta():
    sma = trullas.sma_module(make_bars(trend_series(300, 150, 50)))
    assert sma["short_setup"] and sma["signal"] == "sell"


def test_cruce_bajista_en_tendencia_alcista_es_salida():
    closes = trend_series(300, 50, 150) + [133.0] * 8
    sma = trullas.sma_module(make_bars(closes))
    assert sma["long_setup"]
    assert sma["signal"] == "wait" and "Salida" in sma["note"]
    assert sma["last_cross"]["type"] == "down"


def test_nuevo_cruce_alcista_es_entrada_fresca():
    closes = trend_series(300, 50, 150) + [130.0] * 8 + [160.0] * 3
    sma = trullas.sma_module(make_bars(closes))
    assert sma["signal"] == "buy" and sma["fresh"]
    assert sma["last_cross"]["type"] == "up"


def test_pivotes_fractales():
    points = [10, 11, 12, 13, 14, 20, 14, 13, 12, 11, 10, 9, 8]
    highs, lows = trullas.find_pivots(bars_from(points))
    assert highs == [5]
    assert lows == []


def _double_top(vol_p1, vol_p2):
    # P1 en 110 (índice 10), valle en 95 (índice 20), P2 en 115 (índice 30).
    up1 = trend_series(11, 100, 110)
    down = trend_series(10, 109, 95)
    up2 = trend_series(10, 97, 115)
    tail = trend_series(10, 113, 104)
    points = up1 + down + up2 + tail
    vols = [1000.0] * len(points)
    for i in (9, 10, 11):
        vols[i] = vol_p1
    for i in (29, 30, 31):
        vols[i] = vol_p2
    return bars_from(points, vols)


def test_divergencia_bajista_de_volumen_y_retroceso():
    bars = _double_top(5000, 2000)
    k, _ = trullas.stochastic_slow(bars)
    result = trullas._evaluate_pair(bars, k, 10, 30, "high")
    assert result["direction"] == "bearish" and result["volume"]
    assert result["absolute"]["price"] == pytest.approx(94.5)  # mínimo entre P1 y P2
    p2 = 115.5
    rango = 94.5 - p2
    assert result["range"] == pytest.approx(rango)
    assert result["target66"] == pytest.approx(p2 + 0.66 * rango)
    assert result["target618"] == pytest.approx(p2 + 0.618 * rango)
    assert result["target50"] == pytest.approx(p2 + 0.5 * rango)
    assert result["target66"] < result["target618"] < result["target50"] < p2


def test_sin_divergencia_si_el_volumen_confirma():
    bars = _double_top(2000, 5000)
    k = [50.0] * len(bars)  # estocástico plano: no aporta divergencia
    assert trullas._evaluate_pair(bars, k, 10, 30, "high") is None


def test_divergencia_alcista_proyecta_hacia_arriba():
    points = (trend_series(11, 110, 100) + trend_series(10, 101, 115)
              + trend_series(10, 113, 95) + trend_series(10, 97, 106))
    vols = [1000.0] * len(points)
    for i in (9, 10, 11):
        vols[i] = 5000
    bars = bars_from(points, vols)
    result = trullas._evaluate_pair(bars, [50.0] * len(bars), 10, 30, "low")
    assert result["direction"] == "bullish" and result["volume"]
    assert result["absolute"]["price"] == pytest.approx(115.5)
    assert result["target66"] > result["p2"]["price"]


def test_atr_de_rango_constante():
    bars = [Bar(t=T0 + i * DAY, o=100, h=101, l=99, c=100) for i in range(30)]
    assert trullas.atr(bars) == pytest.approx(2.0)
    vol = trullas.volatility_module(bars, "long", 2)
    assert vol["stop"] == pytest.approx(96.0)
    assert trullas.volatility_module(bars, "short", 2)["stop"] == pytest.approx(104.0)


def test_fuerza_relativa():
    asset = make_bars(trend_series(100, 100, 130))
    bench = make_bars(trend_series(100, 100, 105))
    assert trullas.relative_strength(asset, bench, "XLK")["label"] == "strong"
    assert trullas.relative_strength(bench, asset, "XLK")["label"] == "weak"
    assert trullas.relative_strength(asset, None, None)["label"] == "none"


def test_top_down_bloquea_contra_mercado():
    up = make_bars(trend_series(300, 50, 150))
    down = trullas.trend_of(make_bars(trend_series(300, 150, 50)))
    td = trullas.top_down(up, down, None, {"market": "SPY", "sector": "XLK"})
    assert td["macro_trend"] == "bullish" and not td["aligned"]
    assert trullas.top_down(up, trullas.trend_of(up), None, {"market": "SPY", "sector": None})["aligned"]


def test_analyze_contrato_resumen():
    bars = make_bars(trend_series(300, 50, 150))
    result = trullas.analyze("AAPL", bars, include_series=True)
    assert set(result["summary"]) == {"ticker", "macroTrend", "smaSignal", "divergenceDetected",
                                      "targetPrice66", "targetPrice618", "atrStop"}
    assert result["summary"]["smaSignal"] == "buy"
    assert len(result["series"]["sma200"]) == len(result["bars"]) == 300


def test_analyze_historial_corto():
    assert trullas.analyze("AAPL", make_bars([100.0] * 150))["error"]


def test_endpoint_lista_y_detalle(tmp_db):
    from fastapi.testclient import TestClient
    from app import market
    from app.main import app
    market.clear_cache()
    client = TestClient(app)
    headers = {"X-Auth-Token": "test-token"}
    with patch.object(market, "_fetch_yfinance", return_value=make_bars(trend_series(300, 50, 150))), \
         patch.object(trullas, "sector_of", return_value="Technology"):
        r = client.get("/api/trullas", headers=headers)
        assert r.status_code == 200
        items = r.json()["items"]
        assert items and all("bars" not in i for i in items)
        t = items[0]["ticker"]
        d = client.get(f"/api/trullas?ticker={t}", headers=headers).json()["item"]
        assert d["relative_strength"]["benchmark"] in ("XLK", "SPY", None)
        assert "bars" in d and "series" in d
    assert client.get("/api/trullas?interval=15m", headers=headers).status_code == 422



def test_corto_exige_70_bajo_200():
    # Caída tras una subida: la 200 y la 70 ya bajan, pero la 70 sigue sobre
    # la 200 -> todavía no hay estructura corta (Trullás pide la 70 debajo).
    closes = [100.0] * 200 + trend_series(60, 100, 200) + [90.0] * 8
    sma = trullas.sma_module(make_bars(closes))
    assert sma["slope200"] < 0 and sma["slope70"] < 0 and sma["sma70"] > sma["sma200"]
    assert not sma["short_setup"] and sma["signal"] == "wait"
