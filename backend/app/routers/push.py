"""Registro de suscripciones Web Push y notificación de prueba."""
import json

from fastapi import APIRouter, Depends, HTTPException

from .. import db
from .. import push as push_service
from ..auth import require_token
from ..config import get_settings
from ..models import PushSubscription

router = APIRouter(prefix="/api/push", tags=["push"],
                   dependencies=[Depends(require_token)])


@router.get("/vapid-public-key")
def vapid_public_key() -> dict:
    key = get_settings().vapid_public_key
    if not key:
        raise HTTPException(status_code=503,
                            detail="Push no configurado: falta VAPID_PUBLIC_KEY")
    return {"publicKey": key}


@router.post("/subscribe", status_code=201)
def subscribe(sub: PushSubscription) -> dict:
    if "p256dh" not in sub.keys or "auth" not in sub.keys:
        raise HTTPException(status_code=422, detail="Suscripción sin claves p256dh/auth")
    db.save_subscription(sub.endpoint, json.dumps(sub.keys))
    return {"ok": True}


@router.post("/test")
def send_test() -> dict:
    if not push_service.push_configured():
        raise HTTPException(status_code=503,
                            detail="Push no configurado: faltan claves VAPID")
    sent = push_service.send_to_all(
        "Cross Monitor — prueba",
        "Notificación de prueba. Si la ves, el push funciona.")
    return {"sent": sent, "subscriptions": len(db.get_subscriptions())}
