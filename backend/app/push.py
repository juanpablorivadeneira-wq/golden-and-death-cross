"""Web Push con VAPID (pywebpush): envío y gestión de suscripciones."""
import json
import logging

from pywebpush import WebPushException, webpush

from . import db
from .config import get_settings

logger = logging.getLogger(__name__)


def push_configured() -> bool:
    s = get_settings()
    return bool(s.vapid_public_key and s.vapid_private_key)


def send_to_all(title: str, body: str) -> int:
    """Envía la notificación a todas las suscripciones. Devuelve cuántas OK.

    Las suscripciones caducadas (404/410) se eliminan de la base.
    """
    if not push_configured():
        logger.warning("Push no configurado: faltan claves VAPID")
        return 0

    s = get_settings()
    payload = json.dumps({"title": title, "body": body})
    sent = 0
    for sub in db.get_subscriptions():
        subscription_info = {
            "endpoint": sub["endpoint"],
            "keys": json.loads(sub["keys_json"]),
        }
        try:
            webpush(
                subscription_info=subscription_info,
                data=payload,
                vapid_private_key=s.vapid_private_key,
                vapid_claims={"sub": f"mailto:{s.vapid_claim_email}"},
            )
            sent += 1
        except WebPushException as exc:
            status = exc.response.status_code if exc.response is not None else None
            if status in (404, 410):
                logger.info("Suscripción caducada, eliminando: %s", sub["endpoint"][:60])
                db.delete_subscription(sub["endpoint"])
            else:
                logger.error("Error al enviar push: %s", exc)
    return sent


def notify_cross(ticker: str, regime: str, ma_fast: float, ma_slow: float,
                 price: float, ma_type: str, fast_len: int, slow_len: int) -> int:
    label = "GOLDEN CROSS" if regime == "golden" else "DEATH CROSS"
    direction = "por encima" if regime == "golden" else "por debajo"
    title = f"{label} — {ticker}"
    body = (f"{ma_type.upper()}{fast_len} ({ma_fast:.2f}) cruzó {direction} de "
            f"{ma_type.upper()}{slow_len} ({ma_slow:.2f}). Precio: {price:.2f}")
    return send_to_all(title, body)


def deliver_alerts():
    """Reintentar por dispositivo sin repetir entregas ya confirmadas."""
    if not push_configured():
        return
    settings = get_settings()
    for alert in reversed(db.get_alerts()):
        for sub in db.get_subscriptions():
            # No enviar histórico anterior al alta de este dispositivo.
            if sub["created_at"] > alert["created_at"] or db.alert_delivered(alert["id"], sub["endpoint"]):
                continue
            title = f"{alert['regime'].upper()} CROSS · {alert['ticker']}"
            body = f"Sesión {alert['cross_date']} · {alert['ma_type'].upper()} {alert['fast_len']}/{alert['slow_len']} · Cierre {alert['price']:.2f}"
            try:
                webpush(subscription_info={"endpoint": sub["endpoint"], "keys": json.loads(sub["keys_json"])},
                        data=json.dumps({"title": title, "body": body, "tag": f"cross-{alert['id']}"}),
                        vapid_private_key=settings.vapid_private_key,
                        vapid_claims={"sub": f"mailto:{settings.vapid_claim_email}"}, timeout=10)
                db.mark_delivered(alert["id"], sub["endpoint"])
            except WebPushException as exc:
                status = exc.response.status_code if exc.response is not None else None
                if status in (404, 410):
                    db.delete_subscription(sub["endpoint"])
                else:
                    logger.warning("Entrega pendiente de alerta %s", alert["id"])
            except Exception:
                logger.exception("Entrega pendiente de alerta %s", alert["id"])
