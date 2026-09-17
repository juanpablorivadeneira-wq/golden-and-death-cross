"""Tests del medidor técnico simplificado (medias móviles + osciladores)."""
from app import technical
from conftest import make_bars, trend_series


def test_rsi_all_gains_is_100():
    closes = trend_series(30, 100, 200)  # estrictamente creciente
    assert technical._rsi(closes) == 100.0


def test_rsi_all_losses_is_near_zero():
    closes = trend_series(30, 200, 100)  # estrictamente decreciente
    assert technical._rsi(closes) < 1.0


def test_rsi_insufficient_data_is_none():
    assert technical._rsi(trend_series(5, 100, 110), period=14) is None


def test_macd_positive_in_sustained_uptrend():
    closes = trend_series(60, 100, 300)
    macd_line, signal_line = technical._macd(closes)
    assert macd_line > 0  # EMA rápida por encima de la lenta en una subida sostenida
    assert macd_line > signal_line  # el MACD todavía va para arriba, no revirtió


def test_macd_insufficient_data_is_none():
    assert technical._macd(trend_series(10, 100, 110)) is None


def test_stochastic_at_top_of_range_is_near_100():
    # El último cierre es el máximo de toda la ventana -> %K cercano a 100
    closes = trend_series(30, 100, 200)
    bars = make_bars(closes)
    k, d = technical._stochastic(bars)
    assert k > 95
    assert d > 90  # %D (suavizado) sigue de cerca en una subida sostenida


def test_cci_positive_when_price_spikes_above_recent_average():
    closes = [100.0] * 19 + [130.0]  # plano y después un salto fuerte al final
    bars = make_bars(closes)
    cci = technical._cci(bars, period=20)
    assert cci > 100  # sobrecompra


def test_cci_zero_deviation_is_none():
    bars = make_bars([100.0] * 20)  # sin variación -> desviación media 0
    assert technical._cci(bars, period=20) is None


def test_ma_signals_mostly_buy_in_sustained_uptrend():
    closes = trend_series(220, 100, 400)
    signals = technical._ma_signals(closes)
    assert len(signals) == 12  # 6 períodos x (SMA + EMA)
    assert signals.count("buy") >= 10  # precio muy por encima de casi todas las medias


def test_score_and_level_strong_buy():
    result = technical._score_and_level(["buy"] * 9 + ["sell"] * 1)
    assert result["level"] == "strong_buy"
    assert result["label"] == "Compra fuerte"
    assert result["score"] == 9


def test_score_and_level_neutral():
    result = technical._score_and_level(["buy"] * 5 + ["sell"] * 5)
    assert result["level"] == "neutral"
    assert result["label"] == "Neutral"


def test_score_and_level_strong_sell():
    result = technical._score_and_level(["sell"] * 9 + ["buy"] * 1)
    assert result["level"] == "strong_sell"
    assert result["label"] == "Venta fuerte"


def test_score_and_level_empty_signals_is_none():
    result = technical._score_and_level([])
    assert result["level"] == "none"
    assert result["score"] is None


def test_analyze_insufficient_bars_is_none_for_all_groups():
    bars = make_bars(trend_series(50, 100, 110))  # menos que MIN_BARS
    result = technical.analyze(bars)
    assert result["moving_averages"]["level"] == "none"
    assert result["oscillators"]["level"] == "none"
    assert result["summary"]["level"] == "none"


def test_analyze_sustained_uptrend_is_bullish_overall():
    bars = make_bars(trend_series(250, 100, 400))
    result = technical.analyze(bars)
    assert result["moving_averages"]["level"] in ("buy", "strong_buy")
    assert result["summary"]["level"] in ("buy", "strong_buy")
    assert result["summary"]["score"] is not None and result["summary"]["score"] >= 6
