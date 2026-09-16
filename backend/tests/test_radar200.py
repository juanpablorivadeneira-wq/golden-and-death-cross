import pytest
from app.radar200 import analyze
from conftest import make_bars


def test_distance_uses_price_not_fast_average():
    bars = make_bars([100.] * 199 + [110.])
    result = analyze("TEST", bars)
    assert result["average"] == pytest.approx(100.05)
    assert result["distance_pct"] == pytest.approx((110/100.05-1)*100)
    assert len(result["series"]) == 200


def test_price_below_average():
    result = analyze("TEST", make_bars([100.] * 199 + [90.]))
    assert result["distance_pct"] < 0


def test_exactly_on_average():
    assert analyze("TEST", make_bars([100.] * 200))["distance_pct"] == 0


def test_history_too_short():
    assert analyze("TEST", make_bars([100.] * 199))["error"]


def test_ema_differs_from_sma():
    bars=make_bars([100.] * 200 + [120.] * 10)
    assert analyze("TEST", bars, "ema")["average"] != analyze("TEST", bars, "sma")["average"]
