"""Configuración de la aplicación vía variables de entorno."""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Token compartido: el frontend lo envía en el header X-Auth-Token
    auth_token: str = "cambiar-este-token"

    # Claves Web Push (generar con scripts/generate_vapid.py)
    vapid_public_key: str = ""
    vapid_private_key: str = ""
    vapid_claim_email: str = "admin@example.com"

    # Fuente de datos alternativa (opcional)
    twelve_data_key: str = ""

    # Escaneo periódico
    scan_interval_min: int = 15
    scan_market_hours_only: bool = False

    # Ruta de la base de datos (volumen Docker en producción)
    db_path: str = "/data/monitor.db"

    # Parámetros por defecto del motor
    default_ma_type: str = "ema"
    default_fast_len: int = 50
    default_slow_len: int = 200

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()
