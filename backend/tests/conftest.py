"""Fixtures compartidas: DB temporal, settings de prueba y barras sintéticas."""
import math
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Configuración de prueba ANTES de importar la app
os.environ.setdefault("AUTH_TOKEN", "test-token")
os.environ.setdefault("DB_PATH", "")  # se fija por test en tmp_path

from app.models import Bar  # noqa: E402

DAY = 86400
T0 = 1700000000  # base arbitraria


def make_bars(closes: list[float]) -> list[Bar]:
    """Convierte una lista de cierres en barras OHLC sintéticas."""
    return [Bar(t=T0 + i * DAY, o=c, h=c * 1.01, l=c * 0.99, c=c)
            for i, c in enumerate(closes)]


def trend_series(n: int, start: float, end: float) -> list[float]:
    """Serie lineal de start a end en n puntos."""
    if n == 1:
        return [start]
    step = (end - start) / (n - 1)
    return [start + i * step for i in range(n)]


def sine_series(n: int, base: float, amp: float, period: float) -> list[float]:
    return [base + amp * math.sin(2 * math.pi * i / period) for i in range(n)]


@pytest.fixture
def tmp_db(tmp_path, monkeypatch):
    """DB SQLite aislada por test."""
    from app.config import get_settings
    db_file = tmp_path / "test.db"
    monkeypatch.setenv("DB_PATH", str(db_file))
    get_settings.cache_clear()
    from app import db as db_module
    db_module.init_db()
    yield db_module
    get_settings.cache_clear()
