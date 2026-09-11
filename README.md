# Cross Monitor — Golden / Death Cross PWA

Monitor de cruces Golden/Death (EMA/SMA 50/200, timeframe diario) con:

- Backend FastAPI que escanea la watchlist 24/7 y envía notificaciones
  Web Push al detectar un cambio de régimen.
- PWA instalable en iPhone (iOS 16.4+) con la UI del prototipo original:
  watchlist con tarjetas plegables, gráfico de velas con EMAs y marcadores
  de cruce, medidor de convergencia.
- Despliegue en Synology con Docker, expuesto por Cloudflare Tunnel.

```
iPhone (PWA instalada)
   │  HTTPS
   ▼
Cloudflare Tunnel ──► Synology (Docker)
                        ├── backend  (FastAPI + APScheduler + SQLite)
                        └── frontend (nginx: PWA + proxy /api)
```

## Estructura

```
backend/    API, motor de cruces, scheduler, web push, tests
frontend/   PWA estática (nginx) con proxy /api → backend
scripts/    generate_vapid.py (claves push), generate_icons.py (íconos)
```

## Desarrollo local

Requisitos: Docker y Docker Compose.

```bash
cp .env.example .env
# Editar .env: AUTH_TOKEN obligatorio; claves VAPID si se quiere probar push
python scripts/generate_vapid.py   # requiere: pip install cryptography

docker compose up --build
```

Abrir http://localhost:8080 e ingresar el AUTH_TOKEN. La watchlist inicial
(QQQ, META, GOOGL, AAPL, MSFT, AMD) se crea sola en el primer arranque.

Tests del backend:

```bash
cd backend
pip install -r requirements.txt
python -m pytest tests/ -q
```

## API

Todos los endpoints exigen el header `X-Auth-Token` excepto `/api/health`.

| Método | Ruta | Descripción |
|---|---|---|
| GET | /api/watchlist | Tickers con métricas completas |
| POST | /api/watchlist/{ticker} | Agregar ticker (valida que existan datos) |
| DELETE | /api/watchlist/{ticker} | Eliminar ticker |
| GET | /api/quotes/{ticker}/ohlc | OHLC 2 años + MAs + cruces históricos |
| GET/PUT | /api/settings | Tipo de MA (ema/sma) y períodos |
| GET | /api/push/vapid-public-key | Clave pública para suscribirse |
| POST | /api/push/subscribe | Registrar suscripción push |
| POST | /api/push/test | Notificación de prueba a todas las suscripciones |
| GET | /api/health | Estado, último escaneo, fuente de datos (sin auth) |

## Despliegue en Synology (Portainer)

1. **Imágenes**: al hacer push a `main`, GitHub Actions construye
   `ghcr.io/OWNER/cross-monitor-backend` y `-frontend` (tags `latest` y SHA).
   Si el repositorio es privado, crear un token clásico con `read:packages`
   y registrarlo en Portainer como registro `ghcr.io`.
2. **Stack**: en Portainer → Stacks → Add stack, pegar el contenido de
   `docker-compose.prod.yml` reemplazando `OWNER`, y definir en
   "Environment variables": `AUTH_TOKEN`, `VAPID_PUBLIC_KEY`,
   `VAPID_PRIVATE_KEY`, `VAPID_CLAIM_EMAIL` (y opcionales
   `TWELVE_DATA_KEY`, `SCAN_INTERVAL_MIN`).
3. **Volumen**: la base SQLite queda en el volumen `cross_monitor_data`.
   Incluirlo en el plan de respaldo del NAS (Hyper Backup).

## Cloudflare Tunnel

1. En Zero Trust → Networks → Tunnels, abrir el túnel existente del NAS
   (o crear uno con el conector en Docker).
2. Agregar un "Public hostname": subdominio dedicado
   (p. ej. `cross.midominio.com`) → servicio `http://IP-DEL-NAS:8081`
   (el puerto del frontend en `docker-compose.prod.yml`).
3. Verificar que `https://cross.midominio.com/api/health` responda.

HTTPS es obligatorio: iOS solo permite service workers y push sobre HTTPS.

## Instalación en iPhone

1. Abrir `https://cross.midominio.com` en **Safari**.
2. Ingresar el AUTH_TOKEN cuando la app lo pida.
3. Compartir → **Agregar a pantalla de inicio**.
4. Abrir la app **desde el ícono** (no desde Safari).
5. Tocar **Activar notificaciones** y aceptar el permiso.
6. Probar el push:
   ```bash
   curl -X POST https://cross.midominio.com/api/push/test \
        -H "X-Auth-Token: TU_TOKEN"
   ```
   La notificación debe llegar aunque la app esté cerrada.

## Configuración

| Variable | Default | Descripción |
|---|---|---|
| AUTH_TOKEN | — | Token que exige la API (obligatorio) |
| VAPID_PUBLIC_KEY / VAPID_PRIVATE_KEY | — | Claves Web Push (`scripts/generate_vapid.py`) |
| VAPID_CLAIM_EMAIL | admin@example.com | Contacto del claim VAPID |
| TWELVE_DATA_KEY | vacío | Si se define, se usa Twelve Data en vez de Yahoo |
| SCAN_INTERVAL_MIN | 15 | Minutos entre escaneos de la watchlist |
| SCAN_MARKET_HOURS_ONLY | false | Solo escanear lun-vie 13-22 UTC |

## Decisiones

- **EMA con semilla SMA**: `ema_series` replica exactamente el JS del
  prototipo (la EMA arranca como SMA de los primeros N valores), para que
  los cruces coincidan con lo que mostraba el HTML original.
- **Detección de cruce del scheduler**: se compara el régimen calculado
  contra el último régimen persistido en SQLite; el primer escaneo solo
  registra el régimen (no notifica), evitando una ráfaga de falsas alertas
  al arrancar.
- **Caché de datos**: 5 minutos por ticker en memoria del backend. La UI
  también cachea las series OHLC 5 minutos para no repetir descargas al
  cambiar de ticker.
- **Auth mínima**: un token compartido en header, guardado en IndexedDB.
  Para endurecer más, poner Cloudflare Access delante del subdominio.
- **Un solo puerto expuesto** en producción (frontend); el backend solo es
  alcanzable por la red interna de Docker a través del proxy nginx.
- **Widget de TradingView eliminado**: la pestaña dependía de un script
  externo; el gráfico propio con lightweight-charts vendorizado cubre el
  caso de uso sin depender de CDNs.
