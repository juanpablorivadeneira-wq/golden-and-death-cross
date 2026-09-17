# Cross Monitor — radar diario

Panel de Golden/Death Cross con filtros, convergencia, gráfico por rangos e historial persistente de alertas. No integra servicios de IA ni consume tokens de IA.

Además del monitor de cruces, incluye dos páginas más sobre la misma watchlist compartida (y los mismos grupos de organización, ver "Grupos de watchlist" abajo):

- **Radar MA 200** (`/radar200.html`): distancia de cada ticker a su media de 200 sesiones (SMA/EMA), con tendencia de la media y gráfico de precio vs. media.
- **Análisis Fundamental** (`/fundamentals.html`): métricas de valoración/deuda/rentabilidad/crecimiento/caja/tamaño vía yfinance, cada una con una explicación en lenguaje simple y una mini-tendencia trimestral cuando hay datos suficientes (ingresos, utilidad neta, márgenes, ROE, deuda/patrimonio, current ratio). Incluye 4 semáforos por ticker:
  - **Salud Fundamental**: puntaje +1/-1 por señal (márgenes, ROE, crecimiento, deuda, liquidez, PEG), con vetos de solvencia sector-aware que impiden un veredicto "Saludable" si hay pérdidas netas, deuda extrema (fuera de sectores donde es normal del negocio) o caja libre negativa no explicada por inversión.
  - **Consenso de Analistas**: recomendación promedio + anillo con el desglose real de analistas (compra/mantener/vender) del período más reciente.
  - **Precio Objetivo**: % de potencial vs. el precio objetivo promedio de analistas.
  - **Análisis Técnico**: medidor de aguja (venta fuerte → compra fuerte) calculado con las mismas barras diarias del motor de cruces — 12 señales de medias móviles (SMA/EMA en 6 períodos) + RSI(14), MACD(12,26,9), Estocástico(14,3,3) y CCI(20). Es una versión propia y simplificada del "Technical Rating" de TradingView, no una réplica exacta.

Estos semáforos son apoyo para la lectura, no asesoría financiera ni una señal de compra/venta automática.

## Documentación del estado actual

- [Estado del proyecto](ESTADO_DEL_PROYECTO.md): funciones, ejecución, validaciones y pendientes, actualizado al 17 de septiembre de 2026.
- [Informe de ampliación fundamental](INFORME_ANALISIS_FUNDAMENTAL.md): métricas avanzadas con explicaciones desplegables, histórico anual, calculadora WACC, escenarios editables e informe local descargable.

La sección **Investigación fundamental** está debajo de las métricas básicas. Sus cálculos y generación de informes no consumen tokens de IA. El análisis cualitativo automático con IA no está conectado. Los datos o modelos aún no disponibles se identifican expresamente; el informe detalla los límites.

## Revisión y alertas

- `SCAN_DAILY=true`: una revisión de lunes a viernes a las 17:00 de Nueva York (ajusta el horario de verano). El servidor debe estar encendido. No consulta continuamente.
- El navegador consulta al abrir y al pulsar Actualizar y revisar; no tiene temporizador periódico.
- Solo se usan sesiones anteriores o la sesión actual después de las 17:00 NY para las alertas. El gráfico puede incluir la sesión provisional. Esta política está orientada a acciones de Estados Unidos.
- La primera revisión establece la referencia sin notificar cruces antiguos. Los cruces posteriores se guardan en SQLite y se deduplican por símbolo, sesión y parámetros. Cambiar las medias reinicia la referencia.
- Para modo exclusivamente manual: `SCAN_DAILY=false` y `SCAN_INTERVAL_MIN=0`. Un intervalo positivo solo se aplica si el modo diario está desactivado.
- Web Push requiere claves VAPID y registrar el dispositivo desde Activar notificaciones. El historial funciona sin estas claves. Los fallos de entrega se reintentan en la siguiente revisión para cada dispositivo; se conservan los últimos 100 eventos para envío y consulta.
- Una interrupción del servidor puede retrasar alertas hasta la próxima revisión. No garantiza entrega exactamente una vez si el servidor se interrumpe entre enviar y registrar la entrega.

## Desarrollo local (sin Docker)

Python 3.12, instalar `backend/requirements.txt` y ejecutar `scripts/run_local.py`. El acceso local es automático y limitado a este equipo. Docker conserva `AUTH_TOKEN`. `TWELVE_DATA_KEY` es opcional y no es una contraseña de acceso.

# Cross Monitor — Golden / Death Cross PWA

Monitor de cruces Golden/Death (EMA/SMA 50/200, timeframe diario) con:

- Backend FastAPI que escanea la watchlist una vez al día y envía notificaciones
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
  app/engine.py        medias móviles, cruces (Cross Monitor)
  app/radar200.py      distancia/tendencia a la MA 200 (Radar MA 200)
  app/fundamentals.py  métricas + semáforos vía yfinance (Análisis Fundamental)
  app/fundamental_research.py métricas avanzadas e histórico anual
  app/technical.py     medidor técnico (medias + osciladores) desde las barras diarias
frontend/   PWA estática (nginx) con proxy /api → backend
  public/index.html         Cross Monitor
  public/radar200.html      Radar MA 200
  public/fundamentals.html  Análisis Fundamental
  public/fundamental-research.js calculadoras e informe local
  public/groups.js          grupos de watchlist, compartido por las tres páginas
scripts/    generate_vapid.py (claves push), generate_icons.py (íconos), run_local.py (dev sin Docker)
desktop/    app_entry.py — punto de entrada del ejecutable portable de Windows
```

### Grupos de watchlist

Los tickers se pueden agrupar en carpetas personalizadas (ej. "FANG+2",
"Cripto") desde cualquiera de las tres páginas — el mismo grupo se ve en las
tres, porque viven en el backend (`/api/watchlist/groups`), no por página.
Cada ticker tiene un selector para asignarlo a un grupo (o crear uno nuevo
al vuelo); cada grupo se puede renombrar, reordenar o eliminar desde su
encabezado, incluso si todavía no tiene tickers asignados.

## Desarrollo local (Docker)

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
| GET | /api/watchlist | Tickers con métricas completas (incluye `group`) |
| POST | /api/watchlist/{ticker} | Agregar ticker (valida que existan datos) |
| DELETE | /api/watchlist/{ticker} | Eliminar ticker |
| PUT | /api/watchlist/{ticker}/group | Asignar/quitar el grupo de un ticker |
| GET | /api/watchlist/groups | Listar grupos (orden) |
| POST | /api/watchlist/groups | Crear grupo |
| PUT | /api/watchlist/groups/{name} | Renombrar grupo |
| DELETE | /api/watchlist/groups/{name} | Eliminar grupo (sus tickers vuelven a "Sin categoría") |
| POST | /api/watchlist/groups/{name}/move | Reordenar grupo (`direction`: up/down) |
| GET | /api/quotes/{ticker}/ohlc | OHLC 5 años + MAs + cruces históricos |
| GET | /api/radar200 | Distancia/tendencia a la MA 200 de toda la watchlist, o detalle de un ticker (`?ticker=`) |
| GET | /api/fundamentals/{ticker} | Métricas, 4 semáforos e investigación anual (`research`); `?refresh=true` fuerza recálculo, evita la caché de 5 min |
| GET | /api/alerts | Historial persistente de alertas |
| POST | /api/scan | Ejecutar revisión manual de la watchlist |
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

## Instalación portable en Windows (.exe)

Para correr la app en cualquier PC con Windows sin instalar Python ni
dependencias por separado:

1. **Generar el ejecutable**: `pyinstaller CrossMonitor.spec` (usa
   `desktop/app_entry.py` como punto de entrada — un solo proceso FastAPI
   que sirve la API y el frontend estático juntos, `console=False` para que
   no muestre ventana de consola).
2. **Acceso directo silencioso**: `Iniciar Cross Monitor.vbs` lanza
   `Iniciar Cross Monitor.bat` oculto (`objShell.Run ..., 0, False`), que a
   su vez crea/activa `.venv314` la primera vez que corre (con reintento a
   versiones sin pin si falla la instalación de `pydantic-core`, típico en
   Python muy nuevo sin toolchain de Rust) y arranca el servidor.
3. **Detener**: `Detener Cross Monitor.bat` mata los procesos en los
   puertos 8000/8080.
4. Datos (`AUTH_TOKEN`, base SQLite) en `%LOCALAPPDATA%\CrossMonitor`.

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
| SCAN_DAILY | true | Revisión de lunes a viernes a las 17:00 de Nueva York |
| SCAN_INTERVAL_MIN | 0 | Intervalo adicional desactivado; solo aplica con SCAN_DAILY=false |
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
- **Veto de solvencia sector-aware, no un parche por ticker**: deuda alta no
  penaliza a bancos/utilities reguladas/REITs (es normal y estructural de
  esos negocios), y caja libre negativa no penaliza si el flujo operativo es
  positivo (es inversión, no quema de caja) — la misma regla se verificó
  contra varios tickers reales (ORCL, una utility, un REIT) antes de darla
  por buena, no solo contra el caso que la motivó.
- **Mini-tendencias solo donde el dato aguanta**: yfinance (plan gratuito)
  da ~5 trimestres de estados financieros — insuficiente para un P/E (o
  P/S, P/B, PEG) "trailing" móvil, que necesita combinar precio con una
  ventana de 4 trimestres de ganancias. Por eso esas 4 métricas de
  valoración no tienen mini-tendencia, pero sí la tienen ingresos, utilidad
  neta y los ratios que se calculan sin precio (márgenes, ROE,
  deuda/patrimonio, current ratio) — a esos les alcanzan los mismos ~5
  trimestres porque numerador y denominador salen del mismo estado
  financiero, no de una serie de precio.
- **Medidor técnico propio, no un dato de terceros**: el "Análisis Técnico"
  no viene de ningún proveedor — se calcula en el momento a partir de las
  mismas barras diarias que ya usa el motor de cruces (medias móviles +
  RSI/MACD/Estocástico/CCI), como una versión simplificada y documentada
  del "Technical Rating" de TradingView, no una réplica de su metodología
  exacta (esa combina ~26 indicadores propietarios).
- **Cache-busting manual (`?v=N`)**: `styles.css`, `app.js`, `radar200.js`,
  `fundamentals.js` y `groups.js` se referencian con un número de versión en
  la URL en las tres páginas HTML; hay que subirlo a mano en cada archivo
  que cambie (y en los tres HTML si es `styles.css` o `groups.js`, que son
  compartidos) o el service worker/navegador puede servir una versión vieja.
