"""Análisis fundamental: métricas de valoración/deuda/rentabilidad vía yfinance,
más 3 semáforos (salud propia, consenso de analistas, precio objetivo).

Cada campo puede faltar según el ticker (los ETFs no tienen casi ninguno; los
bancos no reportan debt/equity ni current ratio) — se refleja como None/"Sin
dato" en vez de forzar un valor, y el puntaje de salud ignora los campos
ausentes en lugar de penalizarlos.
"""
import math
import threading
import time

from .engine import clamp, ratio_to_score10

logger_name = __name__

CACHE_TTL_SECONDS = 300
_cache: dict[str, tuple[float, dict]] = {}
_cache_lock = threading.Lock()


class FundamentalsError(Exception):
    """Error al obtener datos fundamentales para un ticker."""


# Sectores (tal como los reporta yfinance) donde una deuda/patrimonio alta es
# normal y estructural del modelo de negocio, no una señal de alerta: bancos
# y financieras se fondean con depósitos/pasivos por diseño, las utilities
# reguladas se financian con deuda de bajo riesgo respaldada por tarifas
# garantizadas, y los REITs están obligados por ley a repartir ~90% de su
# utilidad, por lo que no pueden retener ganancias para crecer sin deuda.
_DEBT_NORMAL_SECTORS = {"Financial Services", "Utilities", "Real Estate"}


# (campo yfinance, etiqueta, explicación de una línea, formato)
# formato: "pct" (0.12 -> "12.00%"), "ratio" (x -> "x.xx"), "money" (x -> "$1.23B"), "raw"
VALUATION_FIELDS = [
    ("trailingPE", "P/E (trailing)", "Precio ÷ beneficio por acción de los últimos doce meses. Compáralo con crecimiento, sector e historia; un múltiplo bajo no demuestra infravaloración.", "ratio"),
    ("priceToSalesTrailing12Months", "P/S", "Capitalización ÷ ventas de los últimos doce meses. Debe interpretarse junto con márgenes y sector; no mide por sí solo si una acción está barata.", "ratio"),
    ("priceToBook", "P/B", "Cuánto pagás por cada dólar de patrimonio contable. <1 puede indicar desconfianza o ganga; >5 común en tech.", "ratio"),
    ("trailingPegRatio", "PEG", "P/E relativo al crecimiento usado por el proveedor. Depende del horizonte y de la estabilidad de ese crecimiento; no determina un precio justo por sí solo.", "ratio"),
]
DEBT_FIELDS = [
    ("debtToEquity", "Deuda/Patrimonio", "Cuánta deuda tiene por cada 100 de capital propio. <50 conservador, 50-150 normal, >200 endeudada. En utilities, inmobiliarias (REITs) y financieras un valor alto es normal del negocio, no una alerta.", "de_ratio"),
    ("currentRatio", "Current ratio", "Activos corrientes ÷ pasivos corrientes; incluye inventarios, no solo efectivo. Un valor bajo requiere revisar el ciclo de caja y el sector.", "ratio"),
]
PROFITABILITY_FIELDS = [
    ("profitMargins", "Margen neto", "De cada 100 en ventas, cuánto es utilidad real. <5% ajustado, 10-20% saludable, >20% muy rentable.", "pct"),
    ("operatingMargins", "Margen operativo", "Rentabilidad del negocio antes de intereses e impuestos. Compara mejor entre empresas del mismo sector que el margen neto.", "pct"),
    ("returnOnEquity", "ROE", "Qué tan bien usa el capital de los accionistas. <10% débil, 15-25% bueno, muy alto (>40%) puede ser por exceso de deuda, no eficiencia.", "pct"),
]
GROWTH_FIELDS = [
    ("totalRevenue", "Ingresos", "El total de ventas de los últimos 12 meses, antes de restar ningún costo. Por sí solo no dice si la empresa gana dinero — mira la tendencia y la utilidad neta de abajo.", "money"),
    ("netIncomeToCommon", "Utilidad neta", "Lo que le queda a la empresa después de todos los costos, impuestos e intereses -- la ganancia real del período. Compará la tendencia, no solo el número de hoy.", "money"),
    ("revenueGrowth", "Crecimiento de ventas (YoY)", "% que crecieron las ventas vs el año anterior. Negativo es alerta, 5-15% sólido, >20% alto crecimiento.", "pct"),
    ("earningsGrowth", "Crecimiento de utilidades (YoY)", "Igual pero en ganancias. Si crece mucho menos que las ventas, puede indicar márgenes en deterioro.", "pct"),
]

# Campos con serie histórica trimestral (mini-tendencia) tomada directamente
# de una fila del income statement trimestral -- mapea el campo de `info` a
# esa fila de yfinance.
DIRECT_TREND_FIELDS = {
    "totalRevenue": "Total Revenue",
    "netIncomeToCommon": "Net Income",
}

# Campos con tendencia = un ratio entre dos filas de los estados financieros
# (sin precio de por medio, a diferencia de P/E, P/S, P/B y PEG -- esos sí
# necesitan combinar precio con ganancias/ventas, y yfinance (plan gratuito)
# solo da ~5 trimestres, insuficiente para un TTM móvil de esas 4 métricas).
# (campo, (statement numerador, fila numerador, statement denominador, fila
# denominador, escala)). La escala solo importa si algún día se muestra el
# valor numérico de la tendencia (hoy el gráfico solo usa la forma, no el
# número) -- debtToEquity va a 100 porque `info["debtToEquity"]` de yfinance
# ya viene como porcentaje (78.4 == 78.4%, no 0.784, ver _fmt "de_ratio"),
# así el mismo campo no queda en dos escalas distintas si más adelante se
# muestra el valor. returnOnEquity acá es del trimestre puntual (utilidad
# trimestral / patrimonio de ese trimestre), no el TTM que muestra la tarjeta
# grande -- se resolvió así a propósito: un ROE TTM móvil necesitaría sumar
# 4 trimestres de utilidad por cada punto, y yfinance (plan gratuito) solo
# da ~5 trimestres en total, dejando apenas 1-2 puntos reales (mismo problema
# que impide una tendencia de P/E). La dirección de la tendencia se preserva
# igual; solo la escala absoluta difiere del número grande.
RATIO_TREND_FIELDS = {
    "profitMargins": ("quarterly_income_stmt", "Net Income", "quarterly_income_stmt", "Total Revenue", 1),
    "operatingMargins": ("quarterly_income_stmt", "Operating Income", "quarterly_income_stmt", "Total Revenue", 1),
    "returnOnEquity": ("quarterly_income_stmt", "Net Income", "quarterly_balance_sheet", "Stockholders Equity", 1),
    "debtToEquity": ("quarterly_balance_sheet", "Total Debt", "quarterly_balance_sheet", "Stockholders Equity", 100),
    "currentRatio": ("quarterly_balance_sheet", "Current Assets", "quarterly_balance_sheet", "Current Liabilities", 1),
}
TREND_FIELDS = {**DIRECT_TREND_FIELDS, **{k: None for k in RATIO_TREND_FIELDS}}
CASH_FIELDS = [
    ("operatingCashflow", "Flujo de caja operativo", "Efectivo que genera el negocio del día a día, antes de gastos de inversión (capex). Si el flujo libre es negativo, revisa la inversión y cómo se financia: flujo operativo positivo no elimina el riesgo de caja.", "money"),
    ("freeCashflow", "Flujo de caja libre", "Lo que le queda después de reinvertir en el negocio (capex). Un valor negativo requiere revisar inversión, liquidez y financiación, aunque el flujo operativo sea positivo.", "money"),
    ("dividendYield", "Dividend yield", "Cuánto reparte en dividendos al año, como % del precio.", "pct"),
    ("payoutRatio", "Payout ratio", "% de la utilidad que destina a dividendos. >80% sostenido es señal de que el dividendo puede estar en riesgo.", "pct"),
]
SIZE_FIELDS = [
    ("marketCap", "Capitalización de mercado", "Precio por acción × acciones en circulación. Mide valor bursátil, no solvencia ni estabilidad garantizada.", "money"),
    ("beta", "Beta", "Sensibilidad histórica al mercado de referencia. No mide el riesgo total ni predice movimientos futuros.", "ratio"),
]

BLOCKS = [
    ("valuation", "Valoración", VALUATION_FIELDS),
    ("debt", "Endeudamiento y solvencia", DEBT_FIELDS),
    ("profitability", "Rentabilidad", PROFITABILITY_FIELDS),
    ("growth", "Crecimiento", GROWTH_FIELDS),
    ("cash", "Caja y dividendos", CASH_FIELDS),
    ("size", "Tamaño y riesgo", SIZE_FIELDS),
]


def _number(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return value if math.isfinite(value) else None


def _normalize_info(source: dict) -> dict:
    """Normalize before presentation and scoring; never guess yield units."""
    info = dict(source)
    for _, _, fields in BLOCKS:
        for field, *_ in fields:
            info[field] = _number(info.get(field))
    for field in ("currentPrice", "regularMarketPrice", "targetMeanPrice", "targetLowPrice",
                  "targetHighPrice", "recommendationMean"):
        info[field] = _number(info.get(field))
    price = info.get("currentPrice") or info.get("regularMarketPrice")
    rate = _number(source.get("dividendRate"))
    # dividendYield has changed units upstream. Annual dividend / price is explicit.
    info["dividendYield"] = rate / price if rate is not None and rate >= 0 and price and price > 0 else None
    info["_yield_note"] = "Calculado: dividendo anual indicado ÷ precio actual. No garantiza pagos futuros." if info["dividendYield"] is not None else "Sin dato: falta dividendo anual o precio válido; no se infiere la unidad del rendimiento del proveedor."
    invalid = set()
    for field in ("trailingPE", "priceToBook", "trailingPegRatio", "debtToEquity", "payoutRatio"):
        if info.get(field) is not None and info[field] < 0:
            invalid.add(field)
            info[field] = None
    info["_invalid_metrics"] = invalid
    return info


def _fmt(value, kind: str) -> str | None:
    if _number(value) is None:
        return None
    try:
        if kind == "pct":
            return f"{value * 100:.2f}%"
        if kind == "de_ratio":
            # yfinance ya entrega debtToEquity como porcentaje (78.4 == 78.4%, no 0.784)
            return f"{value:.1f}%"
        if kind == "ratio":
            return f"{value:.2f}"
        if kind == "money":
            abs_v = abs(value)
            sign = "-" if value < 0 else ""
            if abs_v >= 1e12:
                return f"{sign}${abs_v / 1e12:.2f}T"
            if abs_v >= 1e9:
                return f"{sign}${abs_v / 1e9:.2f}B"
            if abs_v >= 1e6:
                return f"{sign}${abs_v / 1e6:.2f}M"
            return f"{sign}${abs_v:,.0f}"
    except (TypeError, ValueError):
        return None
    return str(value)


# (campo -> (umbral_bueno, umbral_malo, invertido)) para el punto de color por
# métrica en la UI. invertido=True significa "menor es mejor" (P/E, deuda...).
# Campos sin regla (P/B, dividend yield, market cap, beta) quedan "none": son
# informativos, no tienen un "mejor/peor" universal.
_METRIC_STATUS_RULES = {
    "trailingPE": (15, 30, True),
    "priceToSalesTrailing12Months": (2, 10, True),
    "trailingPegRatio": (1, 2, True),
    "debtToEquity": (50, 200, True),
    "currentRatio": (1.5, 1, False),
    "profitMargins": (0.20, 0.05, False),
    "operatingMargins": (0.20, 0.05, False),
    "returnOnEquity": (0.15, 0, False),
    "revenueGrowth": (0.05, 0, False),
    "earningsGrowth": (0.05, 0, False),
    "freeCashflow": (0, 0, False),
    "operatingCashflow": (0, 0, False),
    "payoutRatio": (0.6, 0.8, True),
}


def _metric_status(field: str, value, sector: str | None = None) -> str:
    if value is None or field not in _METRIC_STATUS_RULES:
        return "none"
    good, bad, invert = _METRIC_STATUS_RULES[field]
    # Deuda alta es normal del negocio en estos sectores (ver _DEBT_NORMAL_SECTORS):
    # el punto de color no debe marcarla como alerta aunque supere el umbral genérico.
    if field == "debtToEquity" and sector in _DEBT_NORMAL_SECTORS:
        return "green" if value <= good else "yellow"
    if invert:
        if value <= good:
            return "green"
        if value >= bad:
            return "red"
        return "yellow"
    if value >= good:
        return "green"
    if value <= bad:
        return "red"
    return "yellow"


def _build_blocks(info: dict) -> list[dict]:
    sector = info.get("sector")
    blocks = []
    for key, title, fields in BLOCKS:
        metrics = []
        for field, label, explanation, kind in fields:
            raw = info.get(field)
            display = _fmt(raw, kind)
            if display and kind == "money":
                currency = info.get("currency" if field == "marketCap" else "financialCurrency")
                display = display.replace("$", "") + " " + (currency or "(moneda no informada)")
            metrics.append({
                "key": field,
                "label": label,
                "value": raw,
                "display": "No interpretable" if field in info.get("_invalid_metrics", set()) else (display or "Sin dato"),
                "explanation": explanation + (" " + info["_yield_note"] if field == "dividendYield" and "_yield_note" in info else "") + (" El ratio negativo no permite aplicar los umbrales habituales y se excluye del puntaje." if field in info.get("_invalid_metrics", set()) else "") + (" Serie: trimestres individuales; no equivale al valor TTM. En ROE se usa patrimonio al cierre, no promedio." if field in TREND_FIELDS else "") + (" Moneda de los estados: " + str(info.get("financialCurrency") or "no informada") + "." if kind == "money" and field != "marketCap" else ""),
                "status": _metric_status(field, raw, sector),
                "trend": info.get("_trends", {}).get(field) if field in TREND_FIELDS else None,
            })
        blocks.append({"key": key, "title": title, "metrics": metrics})
    return blocks


def _health_score(info: dict) -> dict:
    """Puntaje +1/-1 por señal (ignorando campos ausentes), con tres alertas
    que pueden impedir un veredicto "Saludable" sin importar cuántas señales
    positivas haya (sin esto, una empresa con pérdidas netas o deuda extrema
    puede seguir saliendo "Saludable" con solo un par de señales de crecimiento
    a favor, porque hoy pesan igual que una pérdida real):

    - Margen neto negativo (la empresa pierde dinero en el período, no es una
      cuestión de crecer más lento sino de no ser rentable todavía).
    - Deuda muy alta, EXCEPTO en sectores donde es normal y estructural del
      negocio (utilities reguladas, inmobiliarias/REITs, financieras).
    - Flujo de caja libre negativo, PERO solo si el flujo de caja OPERATIVO
      también es negativo (o no se conoce) — si el operativo es positivo, la
      caja libre negativa es por invertir fuerte (capex), no por quemar caja
      del negocio en sí (ver caso real: ORCL invierte en IA con caja operativa
      sana; su alerta real es la deuda, no el flujo de caja)."""
    points = 0
    signals = 0

    def score(value, good, bad, invert=False):
        nonlocal points, signals
        if value is None:
            return
        signals += 1
        cond_good = value < good if invert else value > good
        cond_bad = value < bad if not invert else value > bad
        if cond_good:
            points += 1
        elif cond_bad:
            points -= 1

    score(info.get("profitMargins"), 0.10, 0)
    score(info.get("returnOnEquity"), 0.15, 0)
    score(info.get("revenueGrowth"), 0.05, 0)
    score(info.get("earningsGrowth"), 0.05, 0)
    score(info.get("freeCashflow"), 0, 0)
    sector = info.get("sector")
    de = info.get("debtToEquity")
    if de is not None:
        signals += 1
        if de < 50:
            points += 1
        # Deuda alta no resta puntos en sectores donde es normal del negocio
        # (misma excepción que la alerta de solvencia más abajo) — de lo
        # contrario el puntaje numérico penaliza algo que el veredicto no
        # considera una alerta, y las dos lecturas del mismo dato se contradicen.
        elif de > 200 and sector not in _DEBT_NORMAL_SECTORS:
            points -= 1
    cr = info.get("currentRatio")
    if cr is not None:
        signals += 1
        if cr > 1.5:
            points += 1
        elif cr < 1:
            points -= 1
    peg = info.get("trailingPegRatio")
    if peg is not None and peg > 0:
        signals += 1
        if peg < 1:
            points += 1
        elif peg > 3:
            points -= 1

    if signals < 3:
        return {"level": "none", "label": "Datos insuficientes", "detail": "Muy pocas métricas disponibles para este ticker.", "score": None}

    # Alertas: no deberían quedar "tapadas" por buenos márgenes o crecimiento
    # en la suma de puntos — una empresa puede tener buen crecimiento y aun
    # así estar perdiendo dinero o tener un problema de deuda/caja al mismo
    # tiempo. Cada una se afina para no disparar en falso (ver docstring):
    # sector normal-en-deuda, y caja libre negativa que en realidad es
    # inversión con flujo operativo sano.
    red_flags = []
    margins = info.get("profitMargins")
    fcf = info.get("freeCashflow")
    ocf = info.get("operatingCashflow")
    if margins is not None and margins < 0:
        red_flags.append("pérdidas netas (margen neto negativo)")
    if de is not None and de > 200 and sector not in _DEBT_NORMAL_SECTORS:
        red_flags.append("deuda muy alta (Deuda/Patrimonio > 200)")
    if fcf is not None and fcf < 0 and (ocf is None or ocf < 0):
        red_flags.append("flujo de caja negativo (también el operativo, no solo por inversión)" if ocf is not None else "flujo de caja libre negativo")

    # Normaliza a una escala 1-10 independiente de cuántas señales se pudieron evaluar
    # (una empresa con 3 señales y otra con 8 quedan en la misma escala).
    score_10 = ratio_to_score10(points / signals)
    # Las alertas de solvencia deben verse en el detalle sin importar qué rama
    # de veredicto se tome -- si no, quedan calculadas pero nunca mostradas al
    # usuario en los casos que no sean exactamente "buen puntaje + alerta".
    flags_suffix = f" Alertas: {', '.join(red_flags)}." if red_flags else ""
    if points >= 2 and not red_flags:
        return {"level": "green", "label": "Saludable", "detail": f"{points} señales positivas netas sobre {signals} evaluadas.", "score": score_10}
    if points <= -2:
        return {"level": "red", "label": "Señales de alerta", "detail": f"{points} señales negativas netas sobre {signals} evaluadas.{flags_suffix}", "score": score_10}
    if points >= 2 and red_flags:
        return {"level": "yellow", "label": "Mixto", "detail": f"Buen desempeño en otras señales, pero con alertas: {', '.join(red_flags)}.", "score": min(score_10, 6)}
    return {"level": "yellow", "label": "Mixto", "detail": f"Señales mixtas ({points} neto sobre {signals} evaluadas).{flags_suffix}", "score": score_10}


_RECOMMENDATION_LEVEL = {
    "strong_buy": ("green", "Comprar fuerte"),
    "buy": ("green", "Comprar"),
    "hold": ("yellow", "Mantener"),
    "underperform": ("red", "Bajo rendimiento"),
    "sell": ("red", "Vender"),
    "strong_sell": ("red", "Vender fuerte"),
}


def _analyst_consensus(info: dict) -> dict:
    n = info.get("numberOfAnalystOpinions")
    key = info.get("recommendationKey")
    if not n or not key or key not in _RECOMMENDATION_LEVEL:
        return {"level": "none", "label": "Sin cobertura", "analysts": n or 0, "score": None, "breakdown": None}
    level, label = _RECOMMENDATION_LEVEL[key]
    # recommendationMean: 1 (compra fuerte) a 5 (venta) -> invertido a escala 1-10.
    mean = info.get("recommendationMean")
    score_10 = clamp(round((5 - mean) / 4 * 10), 1, 10) if mean is not None else None
    breakdown = info.get("_recommendations_breakdown")
    # numberOfAnalystOpinions y el desglose por categoría vienen de dos tablas
    # distintas de Yahoo y pueden no coincidir (ej. 14 vs 16) -- si mostramos
    # ambos números en la misma tarjeta (el texto arriba y el total dentro del
    # anillo) se contradicen visualmente. Cuando hay desglose real, ese es el
    # conteo que se muestra en el anillo, así que también manda en el texto.
    analysts = sum(breakdown.values()) if breakdown else n
    return {"level": level, "label": label, "analysts": analysts, "score": score_10,
            "breakdown": breakdown}


def _target_price(info: dict) -> dict:
    target = info.get("targetMeanPrice")
    price = info.get("currentPrice") or info.get("regularMarketPrice")
    if not target or not price:
        return {"level": "none", "label": "Sin cobertura", "upside_pct": None, "score": None}
    upside = target / price - 1
    if upside > 0.10:
        level = "green"
    elif upside < -0.10:
        level = "red"
    else:
        level = "yellow"
    # -30% de potencial o peor -> 1; +30% o mejor -> 10.
    score_10 = clamp(round((clamp(upside, -0.30, 0.30) + 0.30) / 0.60 * 10), 1, 10)
    return {
        "level": level,
        "label": f"{upside * 100:+.1f}% vs. objetivo",
        "upside_pct": upside,
        "target_price": target,
        "target_low": info.get("targetLowPrice"),
        "target_high": info.get("targetHighPrice"),
        "score": score_10,
    }


def _fetch_recommendations_breakdown(t) -> dict | None:
    """Conteo real de analistas por categoría (más reciente), no solo el
    promedio. Si falla o viene vacío, se omite -- el anillo simplemente no
    se muestra, no es un dato crítico."""
    try:
        rec = t.recommendations
        if rec is None or rec.empty:
            return None
        row = rec[rec["period"] == "0m"]
        if row.empty:
            # Sin fila del período actual no hay forma confiable de saber cuál
            # fila es "la más reciente" (el orden del DataFrame no está
            # garantizado) -- mejor omitir el anillo que mostrar un dato viejo
            # presentado como si fuera actual.
            return None
        row = row.iloc[0]
        strong_buy = int(row["strongBuy"])
        buy = int(row["buy"])
        hold = int(row["hold"])
        sell = int(row["sell"])
        strong_sell = int(row["strongSell"])
        if strong_buy + buy + hold + sell + strong_sell == 0:
            return None
        return {
            "strong_buy": strong_buy,
            "buy": buy,
            "hold": hold,
            "sell": sell,
            "strong_sell": strong_sell,
        }
    except Exception:  # noqa: BLE001 — el desglose es un plus, nunca debe tumbar la página
        return None


def _statement_row(t, stmt_attr: str, row_name: str):
    """Serie (más antiguo -> más reciente, índice = fecha) de una fila de un
    estado financiero trimestral, o None si el estado/la fila no existe."""
    stmt = getattr(t, stmt_attr, None)
    if stmt is None or stmt.empty or row_name not in stmt.index:
        return None
    return stmt.loc[row_name].dropna().sort_index()


def _fetch_quarterly_trend(t, yf_row_name: str) -> list[float] | None:
    """Serie histórica trimestral directa (ingresos, utilidad neta). yfinance
    (plan gratuito) solo entrega ~4-5 trimestres -- insuficiente para un TTM
    móvil de métricas como P/E, pero alcanza para una mini-tendencia de la
    cifra cruda. None si hay menos de 2 puntos válidos."""
    try:
        row = _statement_row(t, "quarterly_income_stmt", yf_row_name)
        if row is None or len(row) < 2:
            return None
        return [float(v) for v in row.tolist()]
    except Exception:  # noqa: BLE001 — la mini-tendencia es un plus, nunca debe tumbar la página
        return None


def _fetch_ratio_trend(t, num_stmt: str, num_row: str, den_stmt: str, den_row: str,
                       scale: float = 1) -> list[float] | None:
    """Serie trimestral de un ratio (ej. margen neto = utilidad/ingresos)
    calculado directamente de los estados financieros -- sin precio de por
    medio, por lo que no tiene el problema de datos escasos de P/E, P/S, P/B
    y PEG. Empareja numerador y denominador por fecha (pueden venir de
    estados distintos, ej. income statement y balance sheet)."""
    try:
        num = _statement_row(t, num_stmt, num_row)
        den = _statement_row(t, den_stmt, den_row)
        if num is None or den is None:
            return None
        common_dates = sorted(set(num.index) & set(den.index))
        values = [float(num[d] / den[d]) * scale for d in common_dates if den[d] != 0]
        if len(values) < 2:
            return None
        return values
    except Exception:  # noqa: BLE001 — la mini-tendencia es un plus, nunca debe tumbar la página
        return None


def _fetch_info(ticker: str) -> dict:
    import yfinance as yf

    t = yf.Ticker(ticker)
    info = t.info
    if not info or info.get("quoteType") is None:
        raise FundamentalsError(f"Sin datos fundamentales para {ticker}")
    # Los fondos/ETFs no tienen analistas cubriéndolos ni estados financieros
    # propios -- evita los round-trips extra a Yahoo cuyo resultado
    # `analyze()` descartaría de todas formas.
    if info.get("quoteType") == "EQUITY":
        info["_recommendations_breakdown"] = _fetch_recommendations_breakdown(t)
        trends = {field: _fetch_quarterly_trend(t, row_name)
                  for field, row_name in DIRECT_TREND_FIELDS.items()}
        trends.update({field: _fetch_ratio_trend(t, *spec)
                       for field, spec in RATIO_TREND_FIELDS.items()})
        info["_trends"] = trends
        from .fundamental_research import fetch_annual
        info["_annual"] = fetch_annual(t)
    return info


def analyze(ticker: str, force: bool = False) -> dict:
    ticker = ticker.upper()
    now = time.monotonic()
    with _cache_lock:
        hit = _cache.get(ticker)
        if hit and not force and now - hit[0] < CACHE_TTL_SECONDS:
            return hit[1]

    try:
        info = _normalize_info(_fetch_info(ticker))
    except Exception as exc:  # noqa: BLE001 — un ticker roto no debe tumbar la página
        return {"ticker": ticker, "error": str(exc)}

    quote_type = info.get("quoteType", "EQUITY")
    is_fund = quote_type not in ("EQUITY",)
    price = info.get("currentPrice") or info.get("regularMarketPrice")

    from .fundamental_research import build
    research = None if is_fund else build(info, ticker)
    result = {
        "research": research,
        "ticker": ticker,
        "error": None,
        "quote_type": quote_type,
        "is_fund": is_fund,
        "price": price,
        "sector": info.get("sector"),
        "industry": info.get("industry"),
        "semaphores": {
            "health": {"level": "none", "label": "No aplica", "detail": "", "score": None} if is_fund else _health_score(info),
            "analyst_consensus": {"level": "none", "label": "No aplica", "analysts": 0, "score": None, "breakdown": None} if is_fund else _analyst_consensus(info),
            "target_price": {"level": "none", "label": "No aplica", "upside_pct": None, "score": None} if is_fund else _target_price(info),
        },
        "blocks": [] if is_fund else _build_blocks(info),
    }
    with _cache_lock:
        _cache[ticker] = (time.monotonic(), result)
    return result


def clear_cache() -> None:
    with _cache_lock:
        _cache.clear()
