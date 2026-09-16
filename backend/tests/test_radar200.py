"""Tests del radar MA 200: distancia a la media y tendencia de la media."""
import pytest
from app import radar200
from conftest import make_bars, trend_series


def test_distance_uses_price_not_fast_average():
    bars = make_bars([100.] * 199 + [110.])
    result = radar200.analyze("TEST", bars)
    assert result["average"] == pytest.approx(100.05)
    assert result["distance_pct"] == pytest.approx((110/100.05-1)*100)
    assert len(result["series"]) == 200


def test_price_below_average():
    result = radar200.analyze("TEST", make_bars([100.] * 199 + [90.]))
    assert result["distance_pct"] < 0


def test_exactly_on_average():
    assert radar200.analyze("TEST", make_bars([100.] * 200))["distance_pct"] == 0


def test_history_too_short():
    assert radar200.analyze("TEST", make_bars([100.] * 199))["error"]


def test_ema_differs_from_sma():
    bars = make_bars([100.] * 200 + [120.] * 10)
    assert radar200.analyze("TEST", bars, "ema")["average"] != radar200.analyze("TEST", bars, "sma")["average"]


def test_analyze_tendencia_subiendo():
    # Precio en tendencia alcista sostenida: la SMA 200 también debe subir.
    bars = make_bars(trend_series(260, 100, 300))
    result = radar200.analyze("UP", bars, ma_type="sma")
    assert result["error"] is None
    assert result["ma_trend"] == "up"


def test_analyze_tendencia_bajando():
    bars = make_bars(trend_series(260, 300, 100))
    result = radar200.analyze("DOWN", bars, ma_type="sma")
    assert result["error"] is None
    assert result["ma_trend"] == "down"


def test_analyze_sin_suficiente_historial_para_tendencia():
    # 200-209 barras: hay media pero no hay 10 sesiones previas con media válida.
    bars = make_bars(trend_series(205, 100, 150))
    result = radar200.analyze("EDGE", bars, ma_type="sma")
    assert result["error"] is None
    assert result["ma_trend"] is None
