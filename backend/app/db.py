"""SQLite: esquema, semilla inicial y helpers de acceso."""
import os
import sqlite3
import threading
from datetime import datetime, timezone

from .config import get_settings
from .synchronization import serialized

SEED_TICKERS = ["QQQ", "META", "GOOGL", "AAPL", "MSFT", "AMD"]

_lock = threading.Lock()


def _connect() -> sqlite3.Connection:
    settings = get_settings()
    os.makedirs(os.path.dirname(settings.db_path) or ".", exist_ok=True)
    conn = sqlite3.connect(settings.db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db() -> None:
    settings = get_settings()
    with _lock, _connect() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS watchlist (
                ticker TEXT PRIMARY KEY,
                current_regime TEXT,
                last_cross_date TEXT,
                added_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS push_subscriptions (
                endpoint TEXT PRIMARY KEY,
                keys_json TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS alerts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ticker TEXT NOT NULL, regime TEXT NOT NULL, cross_date TEXT NOT NULL,
                ma_type TEXT NOT NULL, fast_len INTEGER NOT NULL, slow_len INTEGER NOT NULL,
                price REAL NOT NULL, created_at TEXT NOT NULL,
                UNIQUE(ticker, regime, cross_date, ma_type, fast_len, slow_len)
            );
            CREATE TABLE IF NOT EXISTS alert_deliveries (
                alert_id INTEGER NOT NULL, endpoint TEXT NOT NULL,
                PRIMARY KEY(alert_id, endpoint)
            );
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
        """)
        # Semilla de watchlist solo en la primera ejecución
        count = conn.execute("SELECT COUNT(*) FROM watchlist").fetchone()[0]
        seeded = conn.execute("SELECT value FROM settings WHERE key='seeded'").fetchone()
        if count == 0 and seeded is None:
            now = datetime.now(timezone.utc).isoformat()
            conn.executemany(
                "INSERT INTO watchlist (ticker, added_at) VALUES (?, ?)",
                [(t, now) for t in SEED_TICKERS],
            )
            conn.execute("INSERT INTO settings (key, value) VALUES ('seeded', '1')")
        # Migración: la referencia antigua podía incluir una vela intradía.
        if not conn.execute("SELECT 1 FROM settings WHERE key='closed_baseline_v1'").fetchone():
            conn.execute("UPDATE watchlist SET current_regime=NULL, last_cross_date=NULL")
            conn.execute("INSERT INTO settings VALUES ('closed_baseline_v1', '1')")
        # Valores por defecto del motor
        defaults = {
            "ma_type": settings.default_ma_type,
            "fast_len": str(settings.default_fast_len),
            "slow_len": str(settings.default_slow_len),
        }
        for k, v in defaults.items():
            conn.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", (k, v))
        conn.commit()


# ── Watchlist ──────────────────────────────────────────────

def get_watchlist() -> list[dict]:
    with _lock, _connect() as conn:
        rows = conn.execute("SELECT * FROM watchlist ORDER BY added_at").fetchall()
        return [dict(r) for r in rows]


def add_ticker(ticker: str) -> bool:
    with _lock, _connect() as conn:
        try:
            conn.execute(
                "INSERT INTO watchlist (ticker, added_at) VALUES (?, ?)",
                (ticker, datetime.now(timezone.utc).isoformat()),
            )
            conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False


def remove_ticker(ticker: str) -> bool:
    with _lock, _connect() as conn:
        cur = conn.execute("DELETE FROM watchlist WHERE ticker = ?", (ticker,))
        conn.commit()
        return cur.rowcount > 0


def update_regime(ticker: str, regime: str, cross_date: str | None) -> None:
    with _lock, _connect() as conn:
        conn.execute(
            "UPDATE watchlist SET current_regime = ?, last_cross_date = ? WHERE ticker = ?",
            (regime, cross_date, ticker),
        )
        conn.commit()


# ── Settings ──────────────────────────────────────────────

def get_setting(key: str, default: str | None = None) -> str | None:
    with _lock, _connect() as conn:
        row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
        return row["value"] if row else default


def set_setting(key: str, value: str) -> None:
    with _lock, _connect() as conn:
        conn.execute(
            "INSERT INTO settings (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )
        conn.commit()


def get_engine_settings() -> tuple[str, int, int]:
    """(ma_type, fast_len, slow_len) actuales."""
    s = get_settings()
    return (
        get_setting("ma_type", s.default_ma_type),
        int(get_setting("fast_len", str(s.default_fast_len))),
        int(get_setting("slow_len", str(s.default_slow_len))),
    )


# ── Suscripciones push ────────────────────────────────────

def save_subscription(endpoint: str, keys_json: str) -> None:
    with _lock, _connect() as conn:
        conn.execute(
            "INSERT INTO push_subscriptions (endpoint, keys_json, created_at) VALUES (?, ?, ?) "
            "ON CONFLICT(endpoint) DO UPDATE SET keys_json = excluded.keys_json",
            (endpoint, keys_json, datetime.now(timezone.utc).isoformat()),
        )
        conn.commit()


def get_subscriptions() -> list[dict]:
    with _lock, _connect() as conn:
        rows = conn.execute("SELECT * FROM push_subscriptions").fetchall()
        return [dict(r) for r in rows]


def delete_subscription(endpoint: str) -> None:
    with _lock, _connect() as conn:
        conn.execute("DELETE FROM push_subscriptions WHERE endpoint = ?", (endpoint,))
        conn.commit()


@serialized
def update_engine_settings(ma_type=None, fast_len=None, slow_len=None):
    """Validar y guardar los parámetros juntos, reiniciando la referencia de alertas."""
    with _lock, _connect() as conn:
        values = dict(conn.execute("SELECT key, value FROM settings").fetchall())
        ma = ma_type if ma_type is not None else values["ma_type"]
        fast = fast_len if fast_len is not None else int(values["fast_len"])
        slow = slow_len if slow_len is not None else int(values["slow_len"])
        if ma not in ("ema", "sma") or not 2 <= fast < slow <= 500:
            raise ValueError("Usa EMA o SMA y períodos 2 <= rápida < lenta <= 500")
        changed = (ma, fast, slow) != (values["ma_type"], int(values["fast_len"]), int(values["slow_len"]))
        if changed:
            conn.executemany("UPDATE settings SET value=? WHERE key=?",
                             [(ma, "ma_type"), (str(fast), "fast_len"), (str(slow), "slow_len")])
            conn.execute("UPDATE watchlist SET current_regime=NULL, last_cross_date=NULL")


def save_alert(metrics, ma_type, fast_len, slow_len):
    with _lock, _connect() as conn:
        cur = conn.execute("""INSERT OR IGNORE INTO alerts
            (ticker,regime,cross_date,ma_type,fast_len,slow_len,price,created_at)
            VALUES (?,?,?,?,?,?,?,?)""", (metrics.ticker, metrics.regime, metrics.cross_date,
            ma_type, fast_len, slow_len, metrics.price, datetime.now(timezone.utc).isoformat()))
        return cur.rowcount > 0


def get_alerts():
    with _lock, _connect() as conn:
        return [dict(r) for r in conn.execute("SELECT * FROM alerts ORDER BY id DESC LIMIT 100")]


def alert_delivered(alert_id, endpoint):
    with _lock, _connect() as conn:
        return conn.execute("SELECT 1 FROM alert_deliveries WHERE alert_id=? AND endpoint=?", (alert_id, endpoint)).fetchone() is not None


def mark_delivered(alert_id, endpoint):
    with _lock, _connect() as conn:
        conn.execute("INSERT OR IGNORE INTO alert_deliveries VALUES (?,?)", (alert_id, endpoint))
