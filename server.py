#!/usr/bin/env python3
"""
Cross Monitor — servidor local
Sirve cross_monitor_v3.html y actúa como proxy hacia Yahoo Finance,
eliminando la dependencia de proxies CORS de terceros.

Uso:
    python server.py            (puerto 8080 por defecto)
    python server.py 9000       (puerto personalizado)

Luego abrir:  http://localhost:8080/cross_monitor_v3.html

Sin dependencias externas: solo librería estándar de Python 3.
"""
import json
import sys
import urllib.parse
import urllib.request
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

# Solo se permite reenviar hacia estos hosts (seguridad)
ALLOWED_HOSTS = {"query1.finance.yahoo.com", "query2.finance.yahoo.com"}

USER_AGENT = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
              "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36")


class Handler(SimpleHTTPRequestHandler):
    def do_GET(self):
        if self.path.startswith("/api/yahoo"):
            self.handle_yahoo_proxy()
        else:
            super().do_GET()

    def handle_yahoo_proxy(self):
        try:
            qs = urllib.parse.urlparse(self.path).query
            params = urllib.parse.parse_qs(qs)
            target = params.get("url", [None])[0]
            if not target:
                return self.send_json(400, {"error": "Falta el parametro url"})

            parsed = urllib.parse.urlparse(target)
            if parsed.scheme != "https" or parsed.hostname not in ALLOWED_HOSTS:
                return self.send_json(403, {"error": "Host no permitido"})

            req = urllib.request.Request(target, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=10) as resp:
                body = resp.read()

            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        except Exception as exc:
            self.send_json(502, {"error": str(exc)})

    def send_json(self, code, obj):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):
        # Log compacto: solo la ruta y el codigo
        print(f"{self.address_string()} - {args[0] if args else ''}")


if __name__ == "__main__":
    import threading
    import webbrowser

    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8080
    server = ThreadingHTTPServer(("0.0.0.0", port), Handler)
    url = f"http://localhost:{port}/cross_monitor_v3.html"
    print(f"Cross Monitor corriendo en  {url}")
    print("Esta ventana debe permanecer abierta. Ctrl+C para detener.")
    # Abrir el navegador automaticamente tras un instante
    threading.Timer(1.0, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nServidor detenido.")
