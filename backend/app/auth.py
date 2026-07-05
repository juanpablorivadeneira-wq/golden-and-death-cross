"""Autenticación simple por token compartido en el header X-Auth-Token."""
import secrets

from fastapi import Header, HTTPException

from .config import get_settings


async def require_token(x_auth_token: str = Header(default="")) -> None:
    expected = get_settings().auth_token
    if not expected or not secrets.compare_digest(x_auth_token, expected):
        raise HTTPException(status_code=401, detail="Token inválido o ausente")
