#!/usr/bin/env python3
"""Genera los íconos PNG de la PWA sin dependencias externas.

Diseño: fondo oscuro (#0C0E12) con dos medias móviles cruzándose,
la rápida dorada (#E8B93E) y la lenta azul (#5B8DEF) — el motivo
del monitor. Produce 180x180, 192x192 y 512x512 en
frontend/public/icons/.
"""
import math
import os
import struct
import zlib

BG = (12, 14, 18)        # #0C0E12
GOLD = (232, 185, 62)    # #E8B93E
BLUE = (91, 141, 239)    # #5B8DEF

OUT_DIR = os.path.join(os.path.dirname(__file__), "..",
                       "frontend", "public", "icons")


def write_png(path: str, size: int, pixels: list[list[tuple]]) -> None:
    def chunk(tag: bytes, data: bytes) -> bytes:
        c = tag + data
        return struct.pack(">I", len(data)) + c + struct.pack(">I", zlib.crc32(c))

    raw = b"".join(
        b"\x00" + b"".join(bytes(px) for px in row) for row in pixels
    )
    ihdr = struct.pack(">IIBBBBB", size, size, 8, 2, 0, 0, 0)
    png = (b"\x89PNG\r\n\x1a\n"
           + chunk(b"IHDR", ihdr)
           + chunk(b"IDAT", zlib.compress(raw, 9))
           + chunk(b"IEND", b""))
    with open(path, "wb") as fh:
        fh.write(png)


def dist_to_curve(x: float, y: float, curve, size: int) -> float:
    """Distancia aproximada de un punto a una curva y=f(x) muestreada."""
    best = 1e9
    steps = 64
    for i in range(steps + 1):
        cx = i / steps * size
        cy = curve(cx / size) * size
        d = math.hypot(x - cx, y - cy)
        if d < best:
            best = d
    return best


def render(size: int) -> list[list[tuple]]:
    # Curvas normalizadas (0..1): la dorada sube, la azul baja; se cruzan al centro
    fast = lambda u: 0.72 - 0.46 * u + 0.06 * math.sin(u * 6.0)   # noqa: E731
    slow = lambda u: 0.30 + 0.42 * u + 0.04 * math.sin(u * 4.5)   # noqa: E731
    thickness = size * 0.055
    radius = size * 0.5
    cx = cy = size / 2

    rows = []
    for yi in range(size):
        row = []
        for xi in range(size):
            # Esquinas redondeadas (máscara circular suave para iOS no es
            # necesaria — iOS recorta solo — pero se ve mejor en Android)
            px = BG
            df = dist_to_curve(xi, yi, fast, size)
            ds = dist_to_curve(xi, yi, slow, size)
            if df < thickness:
                px = GOLD
            elif ds < thickness:
                px = BLUE
            row.append(px)
        rows.append(row)
    return rows


def main() -> None:
    os.makedirs(OUT_DIR, exist_ok=True)
    for size, name in ((180, "icon-180.png"), (192, "icon-192.png"),
                       (512, "icon-512.png")):
        path = os.path.join(OUT_DIR, name)
        write_png(path, size, render(size))
        print(f"OK {path}")


if __name__ == "__main__":
    main()
