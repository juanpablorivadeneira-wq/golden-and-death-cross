#!/usr/bin/env python3
"""Genera un par de claves VAPID para Web Push.

Uso:
    pip install cryptography
    python scripts/generate_vapid.py

Copia la salida en el archivo .env (o en las variables de entorno del
stack de Portainer). La clave privada no debe compartirse.
"""
import base64

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec


def b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def main() -> None:
    key = ec.generate_private_key(ec.SECP256R1())

    # Privada: entero de 32 bytes en base64url (formato que espera pywebpush)
    private_value = key.private_numbers().private_value
    private_b64 = b64url(private_value.to_bytes(32, "big"))

    # Pública: punto EC sin comprimir (65 bytes) en base64url
    public_bytes = key.public_key().public_bytes(
        serialization.Encoding.X962,
        serialization.PublicFormat.UncompressedPoint,
    )
    public_b64 = b64url(public_bytes)

    print("Agrega estas líneas a tu .env:\n")
    print(f"VAPID_PUBLIC_KEY={public_b64}")
    print(f"VAPID_PRIVATE_KEY={private_b64}")


if __name__ == "__main__":
    main()
