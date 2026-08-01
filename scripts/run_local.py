#!/usr/bin/env python3
"""Levanta Cross Monitor sin Docker: backend (uvicorn) en un hilo y el
frontend estático con proxy /api en el hilo principal.

Uso:
    pip install -r backend/requirements.txt
    python scripts/run_local.py

Luego abrir: http://localhost:8080

Variables de entorno (opcionales, mismas que .env): AUTH_TOKEN,
VAPID_PUBLIC_KEY, VAPID_PRIVATE_KEY, VAPID_CLAIM_EMAIL, TWELVE_DATA_KEY,
SCAN_INTERVAL_MIN, SCAN_MARKET_HOURS_ONLY. Si existe un archivo .env en la
raíz del repo, se carga automáticamente.
"""
import os
import sys
import threading
import urllib.error
import urllib.request
import webbrowser
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BACKEND_PORT = 8000
FRONTEND_PORT = 8080
FRONTEND_DIR = os.path.join(ROOT, "frontend", "public")
BACKEND_URL = f"http://127.0.0.1:{BACKEND_PORT}"


def load_dotenv() -> None:
    env_path = os.path.join(ROOT, ".env")
    if not os.path.exists(env_path):
        return
    with open(env_path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            os.environ.setdefault(key.strip(), value.strip())


def start_backend() -> None:
    sys.path.insert(0, os.path.join(ROOT, "backend"))
    os.environ.setdefault("DB_PATH", os.path.join(ROOT, "data", "monitor.db"))
    os.makedirs(os.path.dirname(os.environ["DB_PATH"]), exist_ok=True)
    import uvicorn
    uvicorn.run("app.main:app", host="127.0.0.1", port=BACKEND_PORT, log_level="info")


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        super().__init__(*a, directory=FRONTEND_DIR, **kw)

    def _proxy(self):
        body = None
        if "Content-Length" in self.headers:
            body = self.rfile.read(int(self.headers["Content-Length"]))
        req = urllib.request.Request(BACKEND_URL + self.path, data=body, method=self.command)
        for h in ("X-Auth-Token", "Content-Type"):
            if h in self.headers:
                req.add_header(h, self.headers[h])
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                self.send_response(resp.status)
                for k, v in resp.getheaders():
                    if k.lower() not in ("transfer-encoding", "connection"):
                        self.send_header(k, v)
                self.end_headers()
                self.wfile.write(resp.read())
        except urllib.error.HTTPError as e:
            self.send_response(e.code)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(e.read())
        except urllib.error.URLError:
            self.send_response(502)
            self.end_headers()
            self.wfile.write(b'{"detail":"Backend no disponible"}')

    def do_GET(self):
        (self._proxy() if self.path.startswith("/api/") else super().do_GET())

    def do_POST(self):
        self._proxy()

    def do_PUT(self):
        self._proxy()

    def do_DELETE(self):
        self._proxy()

    def log_message(self, fmt, *args):
        pass  # el log de uvicorn ya es suficiente


def main() -> None:
    load_dotenv()
    os.environ.setdefault("AUTH_TOKEN", "dev-token")
    print(f"AUTH_TOKEN: {os.environ['AUTH_TOKEN']}")

    threading.Thread(target=start_backend, daemon=True).start()

    url = f"http://localhost:{FRONTEND_PORT}/"
    print(f"Cross Monitor: {url}")
    print("Ctrl+C para detener.")
    threading.Timer(1.5, lambda: webbrowser.open(url)).start()

    server = ThreadingHTTPServer(("0.0.0.0", FRONTEND_PORT), Handler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nServidor detenido.")


if __name__ == "__main__":
    main()
