# Informe de ampliación del análisis fundamental

Fecha: 17 de septiembre de 2026.

## Resultado

Se incorporó una sección «Investigación fundamental» bajo las métricas existentes. Sus apartados permanecen plegados para conservar el diseño compacto. Cada métrica avanzada tiene su propia explicación desplegable con fórmula, período, estado del dato y enlace de consulta.

## Etapas implementadas

### 1. Revisión de datos

- Dividend yield calculado con dividendo anual indicado / precio, evitando interpretar una unidad ambigua del proveedor. Si faltan los componentes se muestra Sin dato.
- Deuda/patrimonio expresada como porcentaje y moneda explícita en importes.
- Rechazo de valores no finitos y exclusión de determinados ratios negativos de la clasificación favorable.
- Explicaciones corregidas de current ratio, valoración, caja, tamaño y beta.
- Aclaración de diferencias entre tendencias trimestrales y valores TTM.

### 2. Métricas avanzadas

- EV/EBITDA y P/E futuro reportados por Yahoo, sin atribuir un horizonte 12M no confirmado.
- P/FCF y FCF Yield sobre el último ejercicio, diferenciados de TTM.
- ROIC estimado con capital promedio y tasa efectiva anual.
- Margen bruto, deuda neta/EBITDA, cobertura de intereses y ciclo de conversión de efectivo.
- Conversión FCF/beneficio, dividendos/FCF, recompras brutas y remuneración en acciones.
- Fechas alineadas entre estados; datos faltantes no se sustituyen por cero.
- Ratios que cruzan estados y cotización requieren monedas coincidentes.
- Modelo genérico restringido para empresas financieras; no se ha construido un modelo bancario específico.

### 3. Histórico

Tabla anual de ingresos, FCF, márgenes, ROIC y conversión de caja. No se inventan años ni se convierte una serie corta en una tendencia de cinco años. El CAGR 5Y requiere extremos positivos separados por cinco años completos.

### 4. Coste de capital y escenarios

Calculadora WACC manual con tasa libre de riesgo, prima, beta, coste de deuda, tasa fiscal y pesos. Solicita documentar fuente, fecha y moneda. Calcula el diferencial contra ROIC en puntos porcentuales.

Tres escenarios editables por EPS y múltiplo de salida, horizonte de 3–5 años, descuento, margen de seguridad, potencial y retorno anual. Incluye sensibilidad del caso base. Los valores iniciales son ilustrativos. No es DCF ni una estimación completa de valor intrínseco; excluye dividendos. El crecimiento EPS debe incorporar el efecto de dilución.

Al cambiar supuestos, los resultados anteriores dejan de ser válidos para el informe hasta recalcular.

### 5. Informe local

Generación únicamente mediante botón. Informe Markdown con métricas, períodos, fuentes, histórico, supuestos calculados, evidencia cualitativa introducida por el usuario y pendientes. Se guarda por ticker en el navegador y se puede descargar. No se regenera al actualizar datos.

No se conectó un proveedor de IA: el informe es una recopilación local explicada, no un análisis cualitativo autónomo. La evaluación documental de moat y management permanece pendiente. La aplicación no realiza llamadas a modelos ni consume tokens de IA para estas funciones.

## Límites y trabajo pendiente

- Altman Z-Score: falta seleccionar y validar un modelo sectorial; no está calculado.
- EPS forward 3–5 años: falta una fuente de previsiones documentada.
- Reducción neta de acciones 3Y: falta una serie verificada y ajustada por splits/emisiones.
- Múltiplos históricos 5Y: no implementados por falta de serie homogénea de precios y fundamentales.
- WACC no tiene supuestos automáticos: se calcula en su formulario. La cobertura automática no cuenta estas entradas manuales.
- Yahoo es una fuente secundaria. No se ha realizado contraste automático con documentos regulatorios ni revisión independiente de cada dato reportado.
- Persistencia de informes en localStorage: ligada al navegador y al origen; no se sincroniza con otros dispositivos. Descargar el .md permite conservar una copia independiente.
- No se han cambiado los filtros de salud existentes por un sistema completo de calidad/solvencia sectorial.
- No se ha recompilado el instalador Windows. Los cambios están disponibles en el servidor local del proyecto.

## Validación

- 117 pruebas del backend aprobadas, incluida la suite nueva de cálculos anuales.
- 5 pruebas JavaScript aprobadas: descuento, margen de seguridad, entradas inválidas, WACC e informe.
- Verificación con datos de AAPL: métricas avanzadas, explicaciones desplegables, escenarios y generación de informe.
- Prueba WACC con datos sintéticos: 4% libre de riesgo, prima 5%, beta 1,2, deuda 6%, impuesto 25%, peso deuda 20% → WACC 8,9% y coste del patrimonio 10%.
- Advertencia de deprecación preexistente de Starlette/AnyIO; no impide pasar las pruebas.
- Servidor local reiniciado para cargar los cambios. No se realizó commit ni push.

## Referencias metodológicas

- yfinance, estados financieros: https://ranaroussi.github.io/yfinance/reference/yfinance.financials.html
- Damodaran, coherencia entre flujos y tasas de descuento: https://pages.stern.nyu.edu/~adamodar/New_Home_Page/lectures/val.html
- Berkshire Hathaway, Owner Earnings: https://www.berkshirehathaway.com/letters/1986.html
