# Cross Monitor PWA — Plan de desarrollo y prompt para Claude Code

## PARTE 1 — PLAN

### Objetivo

Convertir el monitor de Golden/Death Cross (actualmente un HTML standalone) en una PWA instalable en iPhone, con detección de cruces corriendo 24/7 en el servidor y notificaciones push aunque la app esté cerrada. Alojada en Synology mediante Docker, expuesta por Cloudflare Tunnel con HTTPS.

### Arquitectura

```
iPhone (PWA instalada)
   │  HTTPS
   ▼
Cloudflare Tunnel ──► Synology (Docker)
                        ├── contenedor "backend"  (FastAPI + APScheduler + SQLite)
                        │     ├── API REST (watchlist, métricas, series OHLC)
                        │     ├── Scheduler: escaneo de cruces cada N minutos
                        │     └── Web Push (VAPID) al detectar cruce
                        └── contenedor "frontend" (nginx)
                              └── PWA: manifest + service worker + UI actual
```

### Decisiones técnicas

| Tema | Decisión | Razón |
|---|---|---|
| Backend | Python 3.12 + FastAPI | Ligero, tipado, async, fácil de contenerizar |
| Datos | yfinance (Yahoo) server-side; Twelve Data opcional por API key | Sin CORS ni proxies; el servidor consulta directo |
| Persistencia | SQLite en volumen Docker | Un solo usuario; cero mantenimiento. Migrable a PostgreSQL después |
| Scheduler | APScheduler dentro del backend | Un contenedor menos que Celery/cron |
| Push | Web Push estándar (VAPID, pywebpush) | Funciona en iOS ≥16.4 con PWA instalada; sin servicios de terceros |
| Frontend | La UI actual (cross_monitor_v3.html) refactorizada a PWA estática | Conservar diseño y lógica visual ya validados |
| HTTPS | Cloudflare Tunnel (subdominio dedicado) | Requisito de iOS para service worker y push; compatible con CGNAT |
| CI/CD | Claude Code → GitHub → Actions → GHCR → Portainer | Mismo pipeline ya usado en otros proyectos |

### Fases

**Fase 1 — Backend funcional (local)**
API REST completa, motor de cálculo EMA/SMA + detección de cruces, scheduler
escaneando la watchlist, SQLite con watchlist y estado de régimen por ticker.
Criterio de salida: `docker compose up` local responde toda la API y el
scheduler registra escaneos en logs.

**Fase 2 — PWA**
Migrar la UI actual a archivos estáticos servidos por nginx. Agregar
manifest.json, service worker, íconos, suscripción push. La UI deja de
calcular: consume la API del backend. Criterio de salida: instalable en
iPhone desde Safari, recibe una notificación de prueba con la app cerrada.

**Fase 3 — Despliegue en Synology**
Compose de producción, volúmenes persistentes, healthchecks, stack en
Portainer, subdominio en Cloudflare Tunnel. Criterio de salida: acceso por
HTTPS desde el iPhone fuera de la red local, push de prueba recibido.

**Fase 4 — Endurecimiento**
Autenticación básica (token en header o Cloudflare Access), backoff y caché
en consultas a Yahoo, logs estructurados, respaldo del volumen SQLite.

### Estimación

Fases 1-2 en una sesión larga de Claude Code; fase 3 depende de acceso al
NAS (30-60 min manuales); fase 4 incremental.

---

## PARTE 2 — PROMPT PARA CLAUDE CODE

Copiar desde aquí hacia abajo en Claude Code, con `cross_monitor_v3.html`
colocado en la raíz del repositorio como referencia visual.

---

Construye una aplicación completa llamada **cross-monitor** siguiendo esta
especificación. Trabaja por fases, crea un plan con TodoWrite antes de
escribir código, y al final de cada fase verifica los criterios de
aceptación antes de continuar.

## Contexto

Existe un prototipo funcional en `cross_monitor_v3.html` (raíz del repo):
un monitor de Golden Cross / Death Cross (EMA/SMA 50/200 en timeframe
diario) con watchlist, gráfico de velas (lightweight-charts), medidor de
convergencia entre medias y alertas. Todo corre en el navegador y consulta
Yahoo Finance mediante proxies CORS, lo cual es frágil. Úsalo como
referencia obligatoria de diseño visual (colores, tipografía, layout,
tarjetas compactas plegables) y de lógica de negocio (cálculo de EMAs,
detección de cruces, brecha porcentual, estimación de sesiones al próximo
cruce).

Hay que convertirlo en: backend en servidor que monitorea 24/7 y envía
push, más una PWA instalable en iPhone que consume ese backend.

## Estructura del repositorio

```
cross-monitor/
├── backend/
│   ├── app/
│   │   ├── main.py            # FastAPI, montaje de routers y scheduler
│   │   ├── config.py          # settings via variables de entorno (pydantic-settings)
│   │   ├── db.py              # SQLite (sqlite3 o SQLAlchemy), init de esquema
│   │   ├── models.py          # dataclasses/pydantic de dominio
│   │   ├── market.py          # descarga de datos: yfinance; Twelve Data si hay TWELVE_DATA_KEY
│   │   ├── engine.py          # EMA, SMA, detección de cruces, brecha, estimación
│   │   ├── scheduler.py       # APScheduler: job de escaneo cada SCAN_INTERVAL_MIN
│   │   ├── push.py            # Web Push VAPID (pywebpush), gestión de suscripciones
│   │   └── routers/
│   │       ├── watchlist.py   # CRUD de tickers
│   │       ├── quotes.py      # métricas y series para la UI
│   │       └── push.py        # registro de suscripciones, notificación de prueba
│   ├── tests/                 # pytest: engine (crítico), market con mocks, API
│   ├── requirements.txt
│   └── Dockerfile
├── frontend/
│   ├── public/
│   │   ├── index.html         # UI migrada del prototipo
│   │   ├── app.js             # lógica de UI consumiendo la API (sin cálculo local)
│   │   ├── styles.css
│   │   ├── manifest.json
│   │   ├── sw.js              # service worker: caché de estáticos + handler de push
│   │   └── icons/             # 180x180, 192x192, 512x512 (generar SVG→PNG simple)
│   ├── nginx.conf             # sirve estáticos y hace proxy /api/ → backend:8000
│   └── Dockerfile
├── docker-compose.yml         # desarrollo local
├── docker-compose.prod.yml    # producción Synology (imágenes de GHCR, volúmenes, healthchecks)
├── .env.example
├── scripts/generate_vapid.py  # genera par de claves VAPID
├── .github/workflows/build.yml  # build multi-arch (amd64) y push a GHCR
└── README.md                  # despliegue completo: local, Portainer, Cloudflare Tunnel
```

## Especificación del backend

**Motor (`engine.py`)** — portar exactamente la lógica del prototipo:
- `ema_series(closes, len)` y `sma_series(closes, len)` idénticas al JS de
  referencia (EMA con semilla SMA de los primeros `len` valores).
- Detección de cruce: cambio de signo de `fast - slow` entre barras
  consecutivas, ignorando barras con MA nula.
- Por ticker producir: precio, ma_fast, ma_slow, régimen (golden/death),
  fecha del último cruce, sesiones desde el cruce, cruce_hoy (bool),
  brecha porcentual `(fast-slow)/slow*100`, convergencia (pendiente de la
  brecha en las últimas 5 barras) y sesiones estimadas al próximo cruce
  (null si divergen o si la estimación supera 250).

**Datos (`market.py`)**:
- Fuente primaria: yfinance, diario, 2 años. Fuente alternativa: Twelve
  Data si `TWELVE_DATA_KEY` está definida (interval=1day, outputsize=600).
- Caché en memoria con TTL de 5 minutos por ticker para no golpear la API.
- Reintentos: 3 con backoff exponencial. Los errores no deben tumbar el
  scheduler ni el endpoint; devolver estado de error por ticker.

**Scheduler (`scheduler.py`)**:
- Job cada `SCAN_INTERVAL_MIN` (default 15): recorre la watchlist, calcula
  el régimen actual y lo compara con el último régimen guardado en DB.
- Si cambió → guardar el nuevo régimen y enviar push a todas las
  suscripciones: título `GOLDEN CROSS — {ticker}` o `DEATH CROSS —
  {ticker}`, cuerpo con MA rápida/lenta y precio.
- Solo escanear en horario relevante si `SCAN_MARKET_HOURS_ONLY=true`
  (default false para simplificar).

**API** (prefijo `/api`):
- `GET /api/watchlist` → tickers con métricas completas (para pintar las tarjetas).
- `POST /api/watchlist/{ticker}` / `DELETE /api/watchlist/{ticker}`.
- `GET /api/quotes/{ticker}/ohlc` → serie OHLC diaria 2 años para el gráfico.
- `GET /api/settings` / `PUT /api/settings` → tipo de MA (ema/sma), períodos.
- `POST /api/push/subscribe` (guarda suscripción), `POST /api/push/test`.
- `GET /api/health` → estado, último escaneo, fuente de datos activa.
- Autenticación: header `X-Auth-Token` comparado con `AUTH_TOKEN` del
  entorno en todos los endpoints excepto `/api/health`. El frontend lo pide
  una vez y lo guarda en IndexedDB.

**DB (SQLite en `/data/monitor.db`, volumen Docker)**: tablas `watchlist`
(ticker, régimen_actual, fecha_último_cruce, added_at), `push_subscriptions`
(endpoint único, claves, created_at), `settings` (clave/valor). Semilla
inicial de watchlist: QQQ, META, GOOGL, AAPL, MSFT, AMD.

## Especificación del frontend (PWA)

- Migrar el diseño del prototipo tal cual: tema oscuro, fila compacta por
  ticker (flecha desplegable, ticker, badge GOLDEN/DEATH, "hace N ses",
  brecha %, precio), detalle plegable con EMAs coloreadas (rápida dorada
  #E8B93E, lenta azul #5B8DEF), medidor de convergencia, modo edición para
  eliminar, botón reintentar en filas con error.
- Gráfico: lightweight-charts (vendorizar el .js en `public/vendor/`, no
  depender de CDN), velas + dos EMAs + marcadores GOLDEN/DEATH en cada
  cruce histórico. Eliminar la pestaña del widget de TradingView.
- Toda la data viene de la API; el frontend no calcula indicadores.
- PWA: manifest (standalone, theme_color #0C0E12), service worker con caché
  de estáticos (network-first para /api), handler de `push` y
  `notificationclick`. Botón "Activar notificaciones" que gestiona permiso
  + suscripción con la clave pública VAPID (expuesta en /api/push/vapid-public-key).
- Responsive: layout de dos columnas en desktop, columna única con
  secciones de scroll independiente en móvil. Safe-areas de iOS
  (env(safe-area-inset-*)).

## Docker y despliegue

- `backend/Dockerfile`: python:3.12-slim, usuario no root, uvicorn en 8000,
  HEALTHCHECK a /api/health.
- `frontend/Dockerfile`: nginx:alpine con nginx.conf (proxy /api →
  backend:8000, headers de caché correctos para sw.js: no-cache).
- `docker-compose.yml` (dev): build local, puerto 8080→frontend, volumen
  ./data para SQLite, variables desde .env.
- `docker-compose.prod.yml`: imágenes `ghcr.io/OWNER/cross-monitor-backend`
  y `-frontend`, restart unless-stopped, healthchecks, red interna; el
  frontend expone un solo puerto interno para el Tunnel.
- `.env.example`: AUTH_TOKEN, VAPID_PUBLIC_KEY, VAPID_PRIVATE_KEY,
  VAPID_CLAIM_EMAIL, TWELVE_DATA_KEY (opcional), SCAN_INTERVAL_MIN.
- GitHub Actions: on push a main, build de ambas imágenes linux/amd64 y
  push a GHCR con tags `latest` y SHA.
- README con: setup local, generación de claves VAPID, despliegue del stack
  en Portainer (pegando el compose de producción), configuración del
  subdominio en Cloudflare Tunnel apuntando al frontend, y los pasos en el
  iPhone (abrir en Safari → Compartir → Agregar a pantalla de inicio →
  abrir la PWA → Activar notificaciones → probar con /api/push/test).

## Criterios de aceptación

1. `docker compose up` local: la UI en http://localhost:8080 muestra la
   watchlist semilla con métricas reales y gráfico de velas con EMAs y
   marcadores de cruce.
2. `pytest` en backend pasa; el motor tiene tests con series sintéticas que
   validan: cruce golden, cruce death, sin cruce, brecha y estimación.
3. Agregar y eliminar tickers desde la UI persiste tras reiniciar contenedores.
4. Con la app cerrada, un cambio de régimen simulado (o /api/push/test)
   entrega notificación push en un navegador de escritorio (la verificación
   en iPhone requiere el despliegue HTTPS de la fase 3).
5. Lighthouse reconoce la app como PWA instalable.
6. Ninguna consulta a datos de mercado ocurre desde el navegador.

## Reglas de trabajo

- Español en comentarios, mensajes de UI y README. Sin emojis.
- Commits atómicos por fase con mensajes descriptivos.
- No inventar claves ni tokens: usar .env.example y documentar generación.
- Si una decisión no está especificada, elegir la opción más simple que
  cumpla los criterios y anotarla en el README bajo "Decisiones".
