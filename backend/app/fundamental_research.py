"""Dated annual fundamentals. No model calls or background work."""
from datetime import datetime, timezone
import math
from urllib.parse import quote


def number(value):
    if isinstance(value, bool):
        return None
    try:
        result = float(value)
        return result if math.isfinite(result) else None
    except (ValueError, TypeError):
        return None


def fetch_annual(ticker):
    result = {}
    for name in ("income_stmt", "balance_sheet", "cashflow"):
        try:
            frame = getattr(ticker, name)
            result[name] = {
                str(date)[:10]: {str(row): number(frame.loc[row, date]) for row in frame.index}
                for date in frame.columns
            }
        except Exception:
            result[name] = {}
    return result


def build(info, ticker):
    annual = info.get("_annual", {})
    income = annual.get("income_stmt", {})
    balance = annual.get("balance_sheet", {})
    cash = annual.get("cashflow", {})
    dates = sorted(income)
    now = datetime.now(timezone.utc).isoformat()
    source = f"https://finance.yahoo.com/quote/{quote(ticker, safe='')}/financials/"
    financial = info.get("financialCurrency")
    quote_currency = info.get("currency")
    same_currency = bool(financial and quote_currency and financial == quote_currency)
    financial_sector = info.get("sector") == "Financial Services"

    def val(table, date, *rows):
        for row in rows:
            v = number(table.get(date, {}).get(row))
            if v is not None:
                return v
        return None

    def divide(a, b):
        return a / b if a is not None and b is not None and b > 0 else None

    def difference(a, b):
        return a - b if a is not None and b is not None else None

    def average(table, date, previous, *rows):
        a, b = val(table, date, *rows), val(table, previous, *rows)
        return (a + b) / 2 if a is not None and b is not None else None

    def annual_values(date, previous):
        revenue = val(income, date, "Total Revenue")
        profit = val(income, date, "Net Income Common Stockholders", "Net Income")
        ebit = val(income, date, "EBIT", "Operating Income")
        ebitda = val(income, date, "EBITDA")
        interest = val(income, date, "Interest Expense")
        ocf = val(cash, date, "Operating Cash Flow")
        capex = val(cash, date, "Capital Expenditure")
        fcf = ocf - abs(capex) if ocf is not None and capex is not None else None
        dividend = val(cash, date, "Common Stock Dividend Paid")
        tax = divide(val(income, date, "Tax Provision"), val(income, date, "Pretax Income"))
        capitals = [difference((val(balance, d, "Total Debt") + val(balance, d, "Stockholders Equity"))
                    if val(balance, d, "Total Debt") is not None and val(balance, d, "Stockholders Equity") is not None else None,
                    val(balance, d, "Cash And Cash Equivalents")) for d in (previous, date)]
        capital = sum(capitals) / 2 if all(v is not None and v > 0 for v in capitals) else None
        roic = divide(ebit * (1-tax), capital) if ebit is not None and tax is not None and 0 <= tax <= 1 else None
        cogs = val(income, date, "Cost Of Revenue")
        inventory = divide(average(balance, date, previous, "Inventory"), cogs)
        receivables = divide(average(balance, date, previous, "Accounts Receivable", "Receivables"), revenue)
        payables = divide(average(balance, date, previous, "Accounts Payable"), cogs)
        ccc = (inventory + receivables - payables) * 365 if all(v is not None for v in (inventory, receivables, payables)) else None
        return dict(revenue=revenue, profit=profit, fcf=fcf,
                    grossMargin=divide(val(income, date, "Gross Profit"), revenue),
                    operatingMargin=divide(val(income, date, "Operating Income"), revenue),
                    roic=roic, conversion=divide(fcf, profit),
                    debtEbitda=divide(difference(val(balance, date, "Total Debt"), val(balance, date, "Cash And Cash Equivalents")), ebitda),
                    interestCoverage=divide(ebit, abs(interest) if interest is not None else None),
                    ccc=ccc, fcfPayout=divide(abs(dividend) if dividend is not None else None, fcf),
                    buybacks=abs(val(cash, date, "Repurchase Of Capital Stock")) if val(cash, date, "Repurchase Of Capital Stock") is not None else None,
                    stockCompensation=val(cash, date, "Stock Based Compensation"))

    history = []
    for i, date in enumerate(dates):
        previous = dates[i-1] if i else ""
        # Ratios using average balances require adjacent fiscal years.
        if previous and not 330 <= (datetime.fromisoformat(date)-datetime.fromisoformat(previous)).days <= 400:
            previous = ""
        point = annual_values(date, previous)
        if financial_sector:
            for key in ("roic", "debtEbitda", "ccc", "conversion", "fcfPayout"):
                point[key] = None
        if any(v is not None for v in point.values()):
            history.append({"date": date, **point})
    dates = [point["date"] for point in history]
    latest = history[-1] if history else {}
    period = latest.get("date", "Ejercicio anual no disponible")
    metrics = []

    def metric(key, label, value, explanation, fmt="ratio", condition="Calculado", date=period, reason=None):
        value = number(value)
        status = condition if value is not None else "Sin dato"
        if reason:
            value, status = None, "No aplicable"
        display = "No aplicable" if reason else "Sin dato"
        if value is not None:
            display = (f"{value*100:.2f}%" if fmt == "pct" else f"{value:.1f} días" if fmt == "days" else f"{value:,.0f} {financial or '(moneda desconocida)'}" if fmt == "money" else f"{value:.2f}×")
        metrics.append(dict(key=key, label=label, value=value, display=display, status="none", trend=None,
                            condition=status, period=date, source=(source.replace("/financials/", "/key-statistics/") if key in ("enterpriseToEbitda", "forwardPE") else source),
                            explanation=f"{explanation} {reason or ''} Estado: {status}. Período: {date}. Fuente: Yahoo Finance. Consulta (UTC): {now[:10]}."))

    sector_reason = "Se requiere un modelo específico para empresas financieras." if financial_sector else None
    metric("enterpriseToEbitda", "EV / EBITDA", info.get("enterpriseToEbitda") if (number(info.get("enterpriseToEbitda")) or 0) > 0 else None, "Múltiplo del proveedor sobre EBITDA; no implica descuento frente a su historia.", condition="Reportado", date="TTM / cotización del proveedor", reason=sector_reason)
    metric("forwardPE", "P/E futuro", info.get("forwardPE") if (number(info.get("forwardPE")) or 0) > 0 else None, "Estimación del proveedor. Horizonte no confirmado: no se etiqueta como próximos 12 meses.", condition="Estimado", date="Horizonte del proveedor")
    cap = number(info.get("marketCap")) if same_currency else None
    fcf = latest.get("fcf")
    metric("priceFcf", "P / FCF anual", divide(cap, fcf), "Capitalización actual ÷ FCF del último ejercicio. Requiere monedas coincidentes y FCF positivo; no es un múltiplo TTM.", reason=sector_reason)
    metric("fcfYield", "FCF Yield anual", divide(fcf, cap), "FCF del último ejercicio ÷ capitalización actual. Solo se calcula con monedas coincidentes.", "pct", reason=sector_reason)
    for key, label, formula, fmt in (
        ("roic", "ROIC estimado", "EBIT × (1 − tasa efectiva anual) ÷ promedio anual de (deuda + patrimonio − efectivo). Sin ajustes de goodwill o arrendamientos; tasa válida entre 0 y 100%.", "pct"),
        ("grossMargin", "Margen bruto anual", "Beneficio bruto ÷ ingresos del mismo ejercicio.", "pct"),
        ("debtEbitda", "Deuda neta / EBITDA", "(Deuda − efectivo al cierre) ÷ EBITDA del mismo ejercicio; EBITDA debe ser positivo.", "ratio"),
        ("interestCoverage", "Cobertura de intereses", "EBIT ÷ gasto de intereses del mismo ejercicio; sin gasto positivo no se calcula.", "ratio"),
        ("ccc", "Ciclo de caja", "365 × (inventario promedio/coste de ventas + cuentas por cobrar promedio/ventas − cuentas por pagar promedio/coste de ventas). Aproximación anual.", "days"),
        ("conversion", "Conversión FCF / beneficio", "(Flujo operativo − valor absoluto del CapEx) ÷ beneficio neto anual positivo. No equivale a Owner Earnings.", "pct"),
        ("fcfPayout", "Dividendos / FCF", "Dividendos comunes pagados ÷ FCF positivo del mismo ejercicio.", "pct"),
        ("buybacks", "Recompras brutas anuales", "Efectivo gastado en recompras. No descuenta emisiones ni demuestra reducción neta de acciones.", "money"),
        ("stockCompensation", "Remuneración en acciones", "Importe del estado de flujos; puede diluir al accionista aunque no sea salida de efectivo inmediata.", "money"),
    ):
        metric(key, label, latest.get(key), formula, fmt, reason=sector_reason if key in ("roic", "debtEbitda", "ccc", "conversion", "fcfPayout") else None)
    cagr = None
    if dates:
        last = datetime.fromisoformat(dates[-1])
        for point in history:
            years = (last-datetime.fromisoformat(point["date"])).days/365.25
            if 4.9 <= years <= 5.1 and (point["revenue"] or 0) > 0 and (latest["revenue"] or 0) > 0:
                cagr = (latest["revenue"]/point["revenue"])**(1/years)-1
    metric("cagr5", "CAGR ingresos 5 años", cagr, "Requiere extremos positivos separados por cinco años completos. No se extrapola un historial más corto.", "pct")
    for key, label, explanation in (
        ("wacc", "WACC", "Pendiente de supuestos verificables de coste de deuda, prima de riesgo, tasa libre de riesgo y estructura de capital."),
        ("spread", "ROIC − WACC", "No se calcula sin WACC documentado; se expresa en puntos porcentuales."),
        ("altman", "Altman Z-Score", "Pendiente de seleccionar una versión válida para el tipo de empresa; no se aplica una fórmula universal."),
        ("epsForward", "Crecimiento EPS 3–5 años", "La fuente conectada no ofrece aquí una previsión documentada para ese horizonte."),
        ("buyback3", "Reducción neta de acciones 3 años", "Pendiente de una serie comparable ajustada por splits y emisiones. No se confunde con recompras brutas."),
    ):
        metric(key, label, None, explanation)
    available = sum(m["value"] is not None for m in metrics)
    return {"blocks": [{"key": "advanced", "title": "Métricas avanzadas", "metrics": metrics}],
            "history": history, "as_of": now, "source": source, "currency": financial,
            "coverage": {"available": available, "total": len(metrics)},
            "scenario": {"price": number(info.get("currentPrice") or info.get("regularMarketPrice")),
                         "eps": number(info.get("trailingEps")) if same_currency else None,
                         "currency": quote_currency, "applicable": not financial_sector,
                         "note": "Modelo por beneficio por acción y múltiplo de salida; no es DCF. EPS TTM debe ser positivo y estar en la moneda de cotización."}}
