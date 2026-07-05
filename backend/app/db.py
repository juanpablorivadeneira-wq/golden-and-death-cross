"""SQLite: esquema, semilla inicial y helpers de acceso."""
import os
import sqlite3
import threading
from datetime import datetime, timezone

from .config import get_settings

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
