# Estado del proyecto — Cross Monitor

Revisión: 17 de septiembre de 2026. Base histórica: `b9bb41a`, más cambios locales de diseño e investigación fundamental todavía sin commit ni push.

## Qué es

Una aplicación de seguimiento de acciones con tres vistas conectadas por un menú superior. Comparte una lista de símbolos y grupos guardados en SQLite. Su propósito es reunir señales de medias móviles, distancia a la tendencia y datos fundamentales en una interfaz compacta.

La aplicación calcula indicadores con código convencional. No necesita modelos de inteligencia artificial ni consume tokens de IA durante su funcionamiento. Las consultas a los proveedores de mercado son independientes del uso de un asistente para desarrollar el proyecto.

## Lo que está implementado

### 1. Cross Monitor

- Medias EMA/SMA, por defecto 50 y 200 sesiones.
- Detección de Golden Cross y Death Cross, fechas y sesiones transcurridas.
- Identificación visual de madurez del cruce.
- Brecha porcentual entre medias y estimación de convergencia.
- Gráfico de velas, medias y marcadores históricos.
- Historial persistente de nuevas alertas, con deduplicación.

El régimen Golden/Death describe la posición actual de las medias; no significa que haya ocurrido un cruce hoy. La estimación de convergencia extrapola movimientos recientes y no garantiza un cruce.

### 2. Radar MA 200

- Distancia entre precio y media de 200 sesiones; SMA o EMA seleccionable.
- Fórmula: `(precio / media200 - 1) × 100`.
- Umbral de cercanía ajustable y filtros cerca/lejos.
- Orden por proximidad, lejanía o símbolo.
- Dirección de la media comparada con diez sesiones atrás.
- Medición histórica con cursor: fecha, cierre, media y porcentaje de distancia.
- Elección de media independiente de los parámetros de Cross Monitor.

El radar informa distancia y tendencia. No tiene un sistema propio de alertas de cercanía.

### 3. Análisis Fundamental

- Métricas de valoración, deuda, rentabilidad, crecimiento, caja y tamaño.
- Explicaciones y mini-tendencias trimestrales donde hay datos suficientes.
- Resumen de salud fundamental mediante reglas, con ajustes por sector.
- Consenso de analistas y desglose de recomendaciones.
- Diferencia entre precio y objetivo promedio de analistas.
- Medidor técnico calculado localmente: doce señales de medias y osciladores RSI, MACD, estocástico y CCI.

Las clasificaciones son heurísticas del proyecto. No equivalen a una auditoría de la empresa ni reproducen exactamente un indicador de TradingView. La disponibilidad y actualidad de los datos dependen de Yahoo. Algunos resúmenes no aplican a fondos u otros instrumentos.

### Investigación fundamental ampliada

Disponible debajo de las métricas básicas, en apartados plegables para conservar espacio:

- Métricas avanzadas: EV/EBITDA, P/E futuro, P/FCF anual, FCF Yield anual, ROIC estimado, margen bruto, deuda neta/EBITDA, cobertura de intereses, ciclo de caja, conversión FCF/beneficio, dividendos/FCF, recompras brutas y remuneración en acciones, cuando hay datos suficientes.
- Cada métrica conserva un desplegable propio con explicación, fórmula, período, condición y enlace de fuente.
- Histórico anual con fechas comparables; CAGR 5Y únicamente con cinco años completos.
- WACC manual con supuestos documentados y comparación contra ROIC en puntos porcentuales.
- Escenarios conservador, base y optimista por EPS y múltiplo de salida, con descuento, margen de seguridad y sensibilidad. Los supuestos iniciales son ilustrativos; no es DCF y excluye dividendos.
- Informe local generado mediante botón, guardado por ticker en este navegador y descargable como Markdown. Incluye evidencia cualitativa introducida por el usuario; no utiliza IA ni se regenera al actualizar cotizaciones.

La revisión corrigió la escala del rendimiento por dividendos, hizo explícitas monedas y unidades y excluyó ciertos ratios negativos o inválidos de una valoración favorable. No se sustituyen datos ausentes por cero.

El informe cualitativo autónomo con IA no está conectado. Altman Z-Score, previsiones EPS 3–5Y, reducción neta de acciones ajustada y múltiplos históricos 5Y siguen pendientes de fuentes o metodología. El WACC se calcula en su formulario, no se obtiene automáticamente del proveedor. El modelo genérico se restringe para empresas financieras, sin implementar aún uno bancario específico.

Detalles, fórmulas y límites: [Informe de análisis fundamental](INFORME_ANALISIS_FUNDAMENTAL.md).

### 4. Interfaz y organización

- Navegación entre las tres herramientas.
- Cabeceras y contadores compactos para priorizar el gráfico.
- Altura del gráfico independiente de la cantidad de tickers.
- Lista con desplazamiento propio y detalles desplegables.
- Cuatro tarjetas fundamentales compactas, en una fila cuando el ancho lo permite; barras segmentadas de rojo a verde y anillo de analistas con más espacio interior.
- Grupos compartidos: crear, asignar, renombrar, reordenar y eliminar sin borrar los símbolos.

## Datos, actualización y alertas

Yahoo mediante yfinance es la fuente principal; Twelve Data es opcional para las cotizaciones. El código descarga cinco años de Yahoo y hasta 1.300 barras de Twelve Data. Esto aporta más historial para calcular la media de 200, pero las primeras 199 barras de la serie descargada siguen sin tener una media completa. Ver cinco años de precios no garantiza una media dibujada desde la primera vela.

La configuración actual del código es:

- `SCAN_DAILY=true`: revisión de lunes a viernes a las 17:00 de Nueva York, con ajuste de horario de verano.
- `SCAN_INTERVAL_MIN=0`: no hay intervalo adicional por defecto.
- El navegador no tiene un temporizador periódico de consultas; sí consulta al abrir, actualizar o realizar acciones.
- Las alertas usan sesiones anteriores o la sesión actual después de las 17:00 NY. Es una política orientada al mercado estadounidense, no un calendario universal de todos los mercados.
- La primera revisión fija la referencia. Cambiar las medias reinicia esa referencia para evitar alertas causadas solo por modificar parámetros.
- Los envíos push fallidos pueden reintentarse por dispositivo en una revisión posterior.

El servidor debe permanecer encendido. Si está apagado o suspendido a la hora programada, no debe asumirse que la revisión ocurrió. El historial local funciona sin Web Push. Para recibir notificaciones fuera de la página hay que configurar VAPID, registrar el dispositivo y verificar una entrega real.

## Arquitectura y archivos principales

| Componente | Ubicación | Función |
|---|---|---|
| API | `backend/app/main.py`, `routers/` | Acceso a datos, grupos, ajustes y alertas |
| Motor de cruces | `backend/app/engine.py` | Medias, cruces y convergencia |
| Datos | `backend/app/market.py` | Descarga, caché y selección de sesiones cerradas |
| Radar | `backend/app/radar200.py` | Distancia y dirección de la MA 200 |
| Fundamental | `backend/app/fundamentals.py` | Datos de empresas y resúmenes |
| Investigación fundamental | `backend/app/fundamental_research.py`, `frontend/public/fundamental-research.js` | Métricas anuales, histórico, calculadoras e informe local |
| Técnico | `backend/app/technical.py` | Medias y osciladores |
| Persistencia | `backend/app/db.py` | Watchlist, grupos, ajustes y alertas |
| Programación | `backend/app/scheduler.py` | Revisión diaria |
| Notificaciones | `backend/app/push.py` | Entrega Web Push |
| Interfaz | `frontend/public/` | Tres páginas, estilos y gráficos |
| Inicio local | `scripts/run_local.py` | Frontend y API en desarrollo |
| Ejecutable | `desktop/app_entry.py`, `CrossMonitor.spec` | Preparación de versión portable Windows |

Hay configuraciones Docker y documentación de despliegue en Synology mediante Cloudflare Tunnel. Tener estos archivos no demuestra que el despliegue esté funcionando.

## Cómo se ejecuta

En desarrollo se usa Python y las dependencias de `backend/requirements.txt`; `scripts/run_local.py` sirve la aplicación local. El ejecutable portable tiene otra entrada y guarda la base de datos en `%LOCALAPPDATA%\CrossMonitor`. Es importante saber qué lanzador está en uso: pueden apuntar a bases distintas.

El acceso local, la autenticación de Docker y la clave opcional de Twelve Data son conceptos separados. `TWELVE_DATA_KEY` sirve al proveedor de cotizaciones; no es una contraseña para entrar a la interfaz.

## Verificación realizada en esta revisión

- Leídos `README.md` y la parte de planificación de `plan_prompt_cross_monitor_pwa.md`.
- Contrastados módulos principales, rutas, configuración, lanzador desktop y consultas del frontend.
- Suite del backend: **117 pruebas aprobadas**, con una advertencia de deprecación de Starlette/AnyIO.
- JavaScript: **5 pruebas aprobadas** para escenarios, WACC e informe.
- Verificación visual con AAPL de desplegables, escenarios, WACC con supuestos sintéticos y guardado del informe. Los supuestos de prueba no permanecen en el informe final.
- Servidor local reiniciado; instalador Windows no recompilado.
- No se probó en esta revisión el ejecutable en otro PC, el despliegue Synology ni la recepción real de notificaciones en iPhone.

## Pendientes y diferencias en la documentación

1. Se actualizó el README: modo diario activo e intervalo cero por defecto.
2. El plan original describe vigilancia continua y una sola PWA. Es una referencia histórica, no el alcance actual: ahora hay tres herramientas y revisión diaria.
3. El README incluye `/api/alerts`, `/api/scan` y el contenido ampliado de la respuesta fundamental.
4. Confirmar Web Push de extremo a extremo antes de considerar terminadas las alertas al móvil.
5. Verificar el portable en un Windows limpio y documentar de forma inequívoca dónde conserva sus datos cada lanzador.
6. Si se requiere continuidad de MA 200 durante todo el período visible, separar el historial de cálculo del período mostrado; cinco años por sí solos no eliminan el calentamiento inicial.
7. Los tests de backend no sustituyen una revisión visual móvil ni pruebas de indisponibilidad del proveedor.

Los informes locales dependen del navegador y del origen; no se sincronizan entre equipos. Yahoo es una fuente secundaria y no se ha implementado contraste automático con documentos regulatorios. La cobertura de datos no equivale a confianza ni calidad empresarial.

## Evolución reciente

- `ebed448`: madurez del cruce, dirección de MA 200 y cinco años de historial.
- `85e70e2`: preparación portable de Windows y lanzador oculto.
- `b9bb41a`: Análisis Fundamental, grupos de watchlist e indicadores técnicos.

- Cambios locales del 16–17 de septiembre: diseño compacto del fundamental, auditoría de unidades, métricas avanzadas, histórico, escenarios, WACC e informes bajo demanda.

Este documento registra el estado observado; no certifica un despliegue de producción ni modifica la configuración de funcionamiento.
