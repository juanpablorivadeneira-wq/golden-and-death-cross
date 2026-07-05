"""Tests del motor: MAs, cruces golden/death, brecha y estimación.

Se usan series sintéticas con períodos cortos (fast=5, slow=20) para que
los casos sean legibles; la lógica es idéntica con 50/200.
"""
import pytest

from app.engine import analyze, ema_series, find_crosses, sma_series, compute_mas
from conftest import make_bars, sine_series, trend_series

FAST, SLOW = 5, 20


def test_sma_basica():
    out = sma_series([1, 2, 3, 4, 5], 3)
    assert out[0] is None and out[1] is None
    assert out[2] == pytest.approx(2.0)
    assert out[3] == pytest.approx(3.0)
    assert out[4] == pytest.approx(4.0)


def test_ema_semilla_sma():
    # La EMA arranca como SMA de los primeros `len` valores (igual que el JS)
    closes = [10, 20, 30, 40, 50]
    out = ema_series(closes, 3)
    assert out[0] is None and out[1] is None
    assert out[2] == pytest.approx(20.0)  # (10+20+30)/3
    k = 2 / 4
    assert out[3] == pytest.approx(40 * k + 20 * (1 - k))


def test_cruce_golden():
    # Baja prolongada y luego subida fuerte: la rápida cruza hacia arriba
    closes = trend_series(60, 100, 60) + trend_series(60, 60, 140)
    bars = make_bars(closes)
    m = analyze("TEST", bars, "ema", FAST, SLOW)
    assert m.error is None
    assert m.regime == "golden"
    fast, slow = compute_mas(closes, "ema", FAST, SLOW)
    crosses = find_crosses(fast, slow, SLOW)
    assert any(c["type"] == "golden" for c in crosses)


def test_cruce_death():
    # Subida prolongada y luego caída fuerte: la rápida cruza hacia abajo
    closes = trend_series(60, 60, 140) + trend_series(60, 140, 50)
    bars = make_bars(closes)
    m = analyze("TEST", bars, "ema", FAST, SLOW)
    assert m.error is None
    assert m.regime == "death"
    assert m.cross_date is not None
    assert m.sessions_since_cross is not None


def test_sin_cruce():
    # Tendencia alcista sostenida: nunca hay cruce (fast siempre > slow)
    closes = trend_series(120, 50, 200)
    fast, slow = compute_mas(closes, "ema", FAST, SLOW)
    assert find_crosses(fast, slow, SLOW) == []
    m = analyze("TEST", make_bars(closes), "ema", FAST, SLOW)
    assert m.regime == "golden"
    assert m.cross_date is None
    assert m.sessions_since_cross is None


def test_cruce_hoy():
    # El cruce ocurre exactamente en la última barra
    closes = trend_series(80, 100, 60)
    fast, slow = compute_mas(closes, "ema", FAST, SLOW)
    # extender hasta que ocurra el cruce y cortar justo ahí
    ext = list(closes)
    while True:
        ext.append(ext[-1] * 1.05)
        fast, slow = compute_mas(ext, "ema", FAST, SLOW)
        crosses = find_crosses(fast, slow, SLOW)
        if crosses and crosses[-1]["idx"] == len(ext) - 1:
            break
        assert len(ext) < 300, "no se produjo el cruce esperado"
    m = analyze("TEST", make_bars(ext), "ema", FAST, SLOW)
    assert m.fresh_cross is True
    assert m.sessions_since_cross == 0


def test_brecha_pct():
    closes = trend_series(120, 50, 200)
    bars = make_bars(closes)
    m = analyze("TEST", bars, "ema", FAST, SLOW)
    fast, slow = compute_mas(closes, "ema", FAST, SLOW)
    n = len(closes) - 1
    esperado = (fast[n] - slow[n]) / slow[n] * 100
    assert m.gap_pct == pytest.approx(esperado)
    assert m.gap_pct > 0


def test_estimacion_convergencia():
    # Subida y luego caída suave: brecha positiva reduciéndose -> convergiendo
    # (la caída es corta y leve para que el cruce aún no ocurra)
    closes = trend_series(100, 50, 150) + trend_series(12, 150, 148)
    m = analyze("TEST", make_bars(closes), "ema", FAST, SLOW)
    assert m.converging is True
    assert m.est_sessions_to_cross is not None
    assert 0 < m.est_sessions_to_cross <= 250


def test_estimacion_divergencia():
    # Tendencia alcista acelerando: la brecha crece -> divergen, sin estimación
    closes = [50 * (1.01 ** i) for i in range(150)]
    m = analyze("TEST", make_bars(closes), "ema", FAST, SLOW)
    assert m.converging is False
    assert m.est_sessions_to_cross is None


def test_historial_insuficiente():
    m = analyze("TEST", make_bars([100.0] * 25), "ema", FAST, SLOW)
    assert m.error is not None


def test_sma_vs_ema_distintas():
    closes = sine_series(120, 100, 20, 40)
    ema_f, _ = compute_mas(closes, "ema", FAST, SLOW)
    sma_f, _ = compute_mas(closes, "sma", FAST, SLOW)
    assert ema_f[-1] != pytest.approx(sma_f[-1])
