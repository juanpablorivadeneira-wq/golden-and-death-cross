"""Punto de entrada del .exe portátil (PyInstaller).

Sirve el backend y el frontend estático desde un único proceso y puerto,
sin depender de Docker ni de un Python externo instalado en la máquina.
Los datos (SQLite) se guardan en %LOCALAPPDATA%\\CrossMonitor para que la
app funcione igual copiada a cualquier carpeta o USB.

El código del backend (paquete `app`) lo compila PyInstaller como módulos
normales (ver CrossMonitor.spec, --paths backend); aquí solo se resuelve
la ruta de datos no-Python (el frontend estático).
"""
import os
import sys
import threading
import time
import webbrowser
from pathlib import Path

PORT = 8000
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

if not getattr(sys, "frozen", False):
    # Modo desarrollo (python desktop/app_entry.py): el paquete `app` vive en backend/.
    sys.path.insert(0, os.path.join(REPO_ROOT, "backend"))

# Build final sin consola (windowed): sys.stdout/stderr quedan en None, y uvicorn
# revienta al configurar su logging (llama sys.stderr.isatty()). Un archivo real
# (aquí NUL) trae todos los métodos que las librerías esperan de un stream.
if sys.stdout is None:
    sys.stdout = open(os.devnull, "w")
if sys.stderr is None:
    sys.stderr = open(os.devnull, "w")


def frontend_dir() -> str:
    """Carpeta del frontend estático: empaquetada por PyInstaller como
    'frontend_public', o frontend/public del repo cuando no está congelado."""
    base = getattr(sys, "_MEIPASS", None)
    if base is not None:
        return os.path.join(base, "frontend_public")
    return os.path.join(REPO_ROOT, "frontend", "public")


def configure_environment() -> None:
    from app.config import DEV_AUTH_TOKEN

    data_dir = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "CrossMonitor"
    data_dir.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("DB_PATH", str(data_dir / "monitor.db"))
    os.environ.setdefault("AUTH_TOKEN", DEV_AUTH_TOKEN)


def build_app():
    from app.main import app
    from fastapi.staticfiles import StaticFiles

    app.mount("/", StaticFiles(directory=frontend_dir(), html=True), name="static")
    return app


def open_browser_when_ready() -> None:
    import urllib.request

    url = f"http://127.0.0.1:{PORT}/"
    for _ in range(60):
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{PORT}/api/health", timeout=1)
            webbrowser.open(url)
            return
        except Exception:
            time.sleep(0.5)


def show_error(message: str) -> None:
    """Sin consola visible (build final), un error silencioso es peor que un
    cuadro de diálogo molesto: al menos el usuario sabe que algo falló."""
    try:
        log_dir = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "CrossMonitor"
        log_dir.mkdir(parents=True, exist_ok=True)
        (log_dir / "error.log").write_text(message, encoding="utf-8")
    except Exception:
        pass
    try:
        import ctypes

        ctypes.windll.user32.MessageBoxW(0, message, "Cross Monitor", 0x10)
    except Exception:
        print(message, file=sys.stderr)


def main() -> None:
    try:
        configure_environment()
        app = build_app()
        threading.Thread(target=open_browser_when_ready, daemon=True).start()

        import uvicorn
        uvicorn.run(app, host="127.0.0.1", port=PORT, log_level="info")
    except OSError as exc:
        show_error(
            f"No se pudo iniciar Cross Monitor en el puerto {PORT}.\n"
            f"¿Ya hay una copia abierta? Cierra esa ventana e intenta de nuevo.\n\n{exc}"
        )
    except Exception:  # noqa: BLE001 — última red de seguridad sin consola visible
        import traceback

        show_error(f"Cross Monitor no pudo iniciar:\n\n{traceback.format_exc()}")


if __name__ == "__main__":
    main()
