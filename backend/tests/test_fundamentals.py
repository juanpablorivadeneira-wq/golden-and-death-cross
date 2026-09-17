"""Tests de fundamentals.py: métricas, semáforos y casos con datos ausentes."""
from unittest.mock import patch

import pytest

from app import fundamentals


@pytest.fixture(autouse=True)
def clean_cache():
    fundamentals.clear_cache()
    yield
    fundamentals.clear_cache()


def full_info(**overrides) -> dict:
    """Info completa estilo AAPL; los tests parciales sobrescriben campos."""
    base = {
        "quoteType": "EQUITY",
        "sector": "Technology",
        "industry": "Consumer Electronics",
        "currentPrice": 200.0,
        "regularMarketPrice": 200.0,
        "trailingPE": 25.0,
        "priceToSalesTrailing12Months": 8.0,
        "priceToBook": 30.0,
        "trailingPegRatio": 1.5,
        "debtToEquity": 40.0,
        "currentRatio": 2.0,
        "profitMargins": 0.25,
        "operatingMargins": 0.30,
        "returnOnEquity": 0.35,
        "revenueGrowth": 0.12,
        "earningsGrowth": 0.20,
        "freeCashflow": 5_000_000_000,
        "dividendYield": 0.005,
        "payoutRatio": 0.15,
        "marketCap": 2_000_000_000_000,
        "beta": 1.1,
        "recommendationKey": "buy",
        "recommendationMean": 2.0,
        "numberOfAnalystOpinions": 30,
        "targetMeanPrice": 230.0,
    }
    base.update(overrides)
    return base


def test_analyze_normal_equity():
    with patch.object(fundamentals, "_fetch_info", return_value=full_info()):
        result = fundamentals.analyze("AAPL")
    assert result["error"] is None
    assert result["is_fund"] is False
    assert result["sector"] == "Technology"
    pe = next(m for b in result["blocks"] if b["key"] == "valuation" for m in b["metrics"] if m["key"] == "trailingPE")
    assert pe["display"] == "25.00"
    assert pe["status"] == "yellow"  # entre 15 (verde) y 30 (rojo)
    debt = next(m for b in result["blocks"] if b["key"] == "debt" for m in b["metrics"] if m["key"] == "debtToEquity")
    assert debt["status"] == "green"  # <50
    pb = next(m for b in result["blocks"] if b["key"] == "valuation" for m in b["metrics"] if m["key"] == "priceToBook")
    assert pb["status"] == "none"  # sin regla universal de bueno/malo
    assert result["semaphores"]["health"]["level"] == "green"
    assert result["semaphores"]["health"]["score"] == 9  # 7 puntos netos sobre 8 señales -> (7/8+1)/2*10
    assert result["semaphores"]["analyst_consensus"] == {"level": "green", "label": "Comprar", "analysts": 30, "score": 8, "breakdown": None}  # (5-2)/4*10
    assert result["semaphores"]["target_price"]["level"] == "green"  # (230/200-1)=15% > 10%


def test_analyze_etf_has_no_metrics():
    with patch.object(fundamentals, "_fetch_info", return_value={"quoteType": "ETF"}):
        result = fundamentals.analyze("QQQ")
    assert result["is_fund"] is True
    assert result["blocks"] == []
    assert result["semaphores"]["health"] == {"level": "none", "label": "No aplica", "detail": "", "score": None}
    assert result["semaphores"]["analyst_consensus"]["level"] == "none"


def test_analyze_partial_data_missing_debt_fields():
    # Bancos: yfinance no reporta debtToEquity ni currentRatio.
    info = full_info(debtToEquity=None, currentRatio=None)
    with patch.object(fundamentals, "_fetch_info", return_value=info):
        result = fundamentals.analyze("JPM")
    debt_block = next(b for b in result["blocks"] if b["key"] == "debt")
    displays = {m["key"]: m["display"] for m in debt_block["metrics"]}
    assert displays["debtToEquity"] == "Sin dato"
    assert displays["currentRatio"] == "Sin dato"
    # El resto de métricas de otros bloques sigue disponible.
    assert result["semaphores"]["health"]["level"] in ("green", "yellow", "red")


def test_analyze_analyst_breakdown_passthrough():
    info = full_info()
    info["_recommendations_breakdown"] = {"buy": 25, "hold": 13, "sell": 6}
    with patch.object(fundamentals, "_fetch_info", return_value=info):
        result = fundamentals.analyze("AAPL")
    assert result["semaphores"]["analyst_consensus"]["breakdown"] == {"buy": 25, "hold": 13, "sell": 6}


def test_analyze_analyst_count_matches_breakdown_total_when_available():
    # Caso real (HIMS): numberOfAnalystOpinions (14) y el desglose por
    # categoría (16) vienen de dos tablas distintas de Yahoo y pueden no
    # coincidir -- si el texto de la tarjeta usa un número y el anillo otro,
    # se contradicen visualmente en la misma tarjeta. Debe mostrarse un solo
    # número, el mismo que suman las barras del anillo.
    info = full_info(numberOfAnalystOpinions=14)
    info["_recommendations_breakdown"] = {"buy": 3, "hold": 13, "sell": 0}
    with patch.object(fundamentals, "_fetch_info", return_value=info):
        result = fundamentals.analyze("HIMS")
    assert result["semaphores"]["analyst_consensus"]["analysts"] == 16


def test_fetch_recommendations_breakdown_aggregates_current_period():
    import pandas as pd

    class FakeTicker:
        recommendations = pd.DataFrame([
            {"period": "0m", "strongBuy": 5, "buy": 20, "hold": 10, "sell": 2, "strongSell": 1},
            {"period": "-1m", "strongBuy": 4, "buy": 18, "hold": 12, "sell": 1, "strongSell": 1},
        ])

    result = fundamentals._fetch_recommendations_breakdown(FakeTicker())
    assert result == {"buy": 25, "hold": 10, "sell": 3}  # strongBuy+buy, hold, sell+strongSell del período "0m"


def test_fetch_recommendations_breakdown_handles_missing_data():
    class FakeTicker:
        recommendations = None

    assert fundamentals._fetch_recommendations_breakdown(FakeTicker()) is None


def test_fetch_recommendations_breakdown_returns_none_without_current_period():
    # Sin fila "0m" no hay forma confiable de saber cuál fila es la más
    # reciente -- se omite en vez de arriesgar mostrar un dato viejo como actual.
    import pandas as pd

    class FakeTicker:
        recommendations = pd.DataFrame([
            {"period": "-1m", "strongBuy": 4, "buy": 18, "hold": 12, "sell": 1, "strongSell": 1},
        ])

    assert fundamentals._fetch_recommendations_breakdown(FakeTicker()) is None


def test_fetch_info_skips_breakdown_for_non_equity():
    # Los fondos/ETFs no tienen analistas -- no vale la pena el round-trip
    # extra a Yahoo para un dato que analyze() descarta de todas formas.
    class FakeTicker:
        info = {"quoteType": "ETF", "symbol": "QQQ"}

    with patch("yfinance.Ticker", return_value=FakeTicker()), \
         patch.object(fundamentals, "_fetch_recommendations_breakdown") as mock_breakdown:
        info = fundamentals._fetch_info("QQQ")
    mock_breakdown.assert_not_called()
    assert "_recommendations_breakdown" not in info


def test_fetch_quarterly_trend_returns_ascending_series():
    import pandas as pd

    class FakeTicker:
        # índice = conceptos, columnas = fechas -- misma forma que entrega yfinance
        quarterly_income_stmt = pd.DataFrame(
            {"2026-07-31": [96221.0], "2026-04-30": [81615.0], "2026-01-31": [68127.0]},
            index=["Total Revenue"],
        )

    result = fundamentals._fetch_quarterly_trend(FakeTicker(), "Total Revenue")
    assert result == [68127.0, 81615.0, 96221.0]  # más antiguo primero


def test_fetch_quarterly_trend_single_point_is_none():
    import pandas as pd

    class FakeTicker:
        quarterly_income_stmt = pd.DataFrame({"2026-07-31": [96221.0]}, index=["Total Revenue"])

    assert fundamentals._fetch_quarterly_trend(FakeTicker(), "Total Revenue") is None


def test_fetch_quarterly_trend_missing_row_is_none():
    import pandas as pd

    class FakeTicker:
        quarterly_income_stmt = pd.DataFrame({"2026-07-31": [1.0]}, index=["Net Income"])

    assert fundamentals._fetch_quarterly_trend(FakeTicker(), "Total Revenue") is None


def test_fetch_ratio_trend_computes_per_quarter_ratio_same_statement():
    import pandas as pd

    class FakeTicker:
        quarterly_income_stmt = pd.DataFrame({
            "2026-07-31": [30.0, 100.0], "2026-04-30": [20.0, 100.0], "2026-01-31": [10.0, 100.0],
        }, index=["Net Income", "Total Revenue"])

    result = fundamentals._fetch_ratio_trend(
        FakeTicker(), "quarterly_income_stmt", "Net Income", "quarterly_income_stmt", "Total Revenue")
    assert result == [0.1, 0.2, 0.3]  # más antiguo primero


def test_fetch_ratio_trend_aligns_by_date_across_two_statements():
    import pandas as pd

    class FakeTicker:
        quarterly_income_stmt = pd.DataFrame(
            {"2026-07-31": [30.0], "2026-04-30": [20.0]}, index=["Net Income"])
        # el balance sheet trae un trimestre extra sin contraparte en el income
        # statement -- debe ignorarse, no romper el emparejamiento por fecha.
        quarterly_balance_sheet = pd.DataFrame(
            {"2026-07-31": [200.0], "2026-04-30": [100.0], "2026-01-31": [50.0]}, index=["Stockholders Equity"])

    result = fundamentals._fetch_ratio_trend(
        FakeTicker(), "quarterly_income_stmt", "Net Income",
        "quarterly_balance_sheet", "Stockholders Equity")
    assert result == [0.2, 0.15]  # 20/100 (04-30), 30/200 (07-31), en ese orden


def test_fetch_ratio_trend_skips_zero_denominator():
    import pandas as pd

    class FakeTicker:
        quarterly_income_stmt = pd.DataFrame({
            "2026-07-31": [30.0, 100.0], "2026-04-30": [20.0, 0.0],
        }, index=["Net Income", "Total Revenue"])

    result = fundamentals._fetch_ratio_trend(
        FakeTicker(), "quarterly_income_stmt", "Net Income", "quarterly_income_stmt", "Total Revenue")
    assert result is None  # el único punto con denominador válido no alcanza para una tendencia


def test_fetch_ratio_trend_missing_statement_is_none():
    class FakeTicker:
        pass  # sin quarterly_balance_sheet

    assert fundamentals._fetch_ratio_trend(
        FakeTicker(), "quarterly_income_stmt", "Net Income",
        "quarterly_balance_sheet", "Stockholders Equity") is None


def test_analyze_profitability_and_debt_blocks_include_ratio_trends():
    info = full_info()
    info["_trends"] = {
        "profitMargins": [0.20, 0.22, 0.25],
        "operatingMargins": None,
        "returnOnEquity": [0.30, 0.33, 0.35],
        "debtToEquity": [0.35, 0.38, 0.40],
        "currentRatio": [2.1, 2.0, 2.0],
    }
    with patch.object(fundamentals, "_fetch_info", return_value=info):
        result = fundamentals.analyze("AAPL")
    profitability = next(b for b in result["blocks"] if b["key"] == "profitability")
    debt = next(b for b in result["blocks"] if b["key"] == "debt")
    margin = next(m for m in profitability["metrics"] if m["key"] == "profitMargins")
    operating = next(m for m in profitability["metrics"] if m["key"] == "operatingMargins")
    roe = next(m for m in profitability["metrics"] if m["key"] == "returnOnEquity")
    de = next(m for m in debt["metrics"] if m["key"] == "debtToEquity")
    cr = next(m for m in debt["metrics"] if m["key"] == "currentRatio")
    assert margin["trend"] == [0.20, 0.22, 0.25]
    assert operating["trend"] is None
    assert roe["trend"] == [0.30, 0.33, 0.35]
    assert de["trend"] == [0.35, 0.38, 0.40]
    assert cr["trend"] == [2.1, 2.0, 2.0]


def test_analyze_growth_block_includes_trend_for_revenue_and_income():
    info = full_info(totalRevenue=96_221_000_000, netIncomeToCommon=26_422_000_000)
    info["_trends"] = {
        "totalRevenue": [68_127.0, 81_615.0, 96_221.0],
        "netIncomeToCommon": None,  # ej. datos insuficientes para ese campo puntual
    }
    with patch.object(fundamentals, "_fetch_info", return_value=info):
        result = fundamentals.analyze("NVDA")
    growth = next(b for b in result["blocks"] if b["key"] == "growth")
    revenue = next(m for m in growth["metrics"] if m["key"] == "totalRevenue")
    income = next(m for m in growth["metrics"] if m["key"] == "netIncomeToCommon")
    revenue_growth_pct = next(m for m in growth["metrics"] if m["key"] == "revenueGrowth")
    assert revenue["trend"] == [68_127.0, 81_615.0, 96_221.0]
    assert income["trend"] is None
    assert revenue_growth_pct["trend"] is None  # campos sin serie histórica nunca traen "trend"


def test_fetch_info_fetches_breakdown_for_equity():
    class FakeTicker:
        info = {"quoteType": "EQUITY", "symbol": "AAPL"}

    with patch("yfinance.Ticker", return_value=FakeTicker()), \
         patch.object(fundamentals, "_fetch_recommendations_breakdown", return_value={"buy": 1, "hold": 0, "sell": 0}) as mock_breakdown:
        info = fundamentals._fetch_info("AAPL")
    mock_breakdown.assert_called_once()
    assert info["_recommendations_breakdown"] == {"buy": 1, "hold": 0, "sell": 0}


def test_analyze_no_analyst_coverage():
    info = full_info(recommendationKey=None, numberOfAnalystOpinions=0, targetMeanPrice=None)
    with patch.object(fundamentals, "_fetch_info", return_value=info):
        result = fundamentals.analyze("SMALLCAP")
    assert result["semaphores"]["analyst_consensus"] == {"level": "none", "label": "Sin cobertura", "analysts": 0, "score": None, "breakdown": None}
    assert result["semaphores"]["target_price"]["level"] == "none"


def test_analyze_high_debt_and_unexplained_negative_fcf_caps_health_at_yellow():
    # Sin dato de flujo operativo, una caja libre negativa no se puede
    # distinguir de quema de caja real -> se marca por precaución.
    info = full_info(debtToEquity=251.7, freeCashflow=-45_850_000_000)
    with patch.object(fundamentals, "_fetch_info", return_value=info):
        result = fundamentals.analyze("ORCL")
    health = result["semaphores"]["health"]
    assert health["level"] == "yellow"
    assert health["label"] == "Mixto"
    assert "deuda muy alta" in health["detail"]
    assert "flujo de caja libre negativo" in health["detail"]
    assert health["score"] <= 6  # tope aplicado por el veto, aunque el puntaje crudo sea más alto


def test_analyze_orcl_real_profile_debt_flags_but_capex_fcf_does_not():
    # Caso real reportado: ORCL tiene márgenes/ROE/crecimiento fuertes, deuda
    # muy alta (251.7) y caja libre negativa (-$45.85B) -- pero su flujo de
    # caja OPERATIVO es positivo (+$46.94B): la caja libre negativa es por
    # invertir fuerte en capex de IA, no por quemar caja del negocio. Solo la
    # deuda debería quedar marcada, no el flujo de caja.
    info = full_info(sector="Technology", debtToEquity=251.7,
                     freeCashflow=-45_850_000_000, operatingCashflow=46_940_000_000)
    with patch.object(fundamentals, "_fetch_info", return_value=info):
        result = fundamentals.analyze("ORCL")
    health = result["semaphores"]["health"]
    assert health["level"] == "yellow"
    assert "deuda muy alta" in health["detail"]
    assert "flujo de caja" not in health["detail"]


def test_analyze_regulated_utility_high_debt_is_not_flagged():
    # Una utility regulada con deuda alta es normal del negocio (tarifas
    # garantizadas), no una alerta -- no debería impedir "Saludable".
    info = full_info(sector="Utilities", debtToEquity=250.0, currentRatio=1.2,
                     freeCashflow=2_000_000_000, operatingCashflow=3_000_000_000)
    with patch.object(fundamentals, "_fetch_info", return_value=info):
        result = fundamentals.analyze("NEE")
    health = result["semaphores"]["health"]
    assert health["level"] == "green"
    assert health["label"] == "Saludable"


def test_analyze_debt_not_penalized_in_score_for_exempt_sector():
    # El mismo dato (deuda alta en un sector donde es normal) no puede ser
    # "neutral" para el veredicto y "malo" para el puntaje numérico que lo
    # respalda -- antes, el punto de deuda restaba en el loop de puntaje aunque
    # el veto ya lo eximiera, contradiciendo el propio veredicto "Saludable".
    info = full_info(sector="Real Estate", debtToEquity=250.0, currentRatio=1.2)
    with patch.object(fundamentals, "_fetch_info", return_value=info):
        result = fundamentals.analyze("O")
    debt = next(m for b in result["blocks"] if b["key"] == "debt" for m in b["metrics"] if m["key"] == "debtToEquity")
    assert debt["status"] == "yellow"  # alto pero normal del sector, no "red"
    health = result["semaphores"]["health"]
    assert health["level"] == "green"
    assert health["label"] == "Saludable"


def test_analyze_debt_penalized_in_score_for_normal_sector():
    # Caso de control: en un sector donde la deuda alta SÍ es una alerta, debe
    # seguir restando puntos y marcando rojo el dato individual, como antes.
    info = full_info(sector="Technology", debtToEquity=250.0, currentRatio=1.2)
    with patch.object(fundamentals, "_fetch_info", return_value=info):
        result = fundamentals.analyze("XYZ")
    debt = next(m for b in result["blocks"] if b["key"] == "debt" for m in b["metrics"] if m["key"] == "debtToEquity")
    assert debt["status"] == "red"
    assert "deuda muy alta" in result["semaphores"]["health"]["detail"]


def test_analyze_solvency_flags_surface_outside_mixed_positive_branch():
    # Antes, red_flags solo se mostraba en la rama "buen puntaje + alerta" --
    # una empresa con señales flojas Y deuda muy alta perdía la advertencia de
    # deuda por completo (se veía "Señales mixtas" sin mencionar el motivo).
    info = full_info(
        sector="Technology", debtToEquity=250.0, currentRatio=1.2, trailingPegRatio=1.5,
        profitMargins=-0.05, returnOnEquity=-0.05, revenueGrowth=0.10, earningsGrowth=0.15,
        freeCashflow=2_000_000_000,
    )
    with patch.object(fundamentals, "_fetch_info", return_value=info):
        result = fundamentals.analyze("XYZ2")
    health = result["semaphores"]["health"]
    assert health["level"] == "yellow"
    assert health["label"] == "Mixto"
    assert "deuda muy alta" in health["detail"]


def test_analyze_negative_margin_caps_health_even_with_good_growth():
    # Caso real (INTC): márgen neto y ROE negativos (la empresa pierde dinero)
    # pero con buen crecimiento, deuda baja y caja libre positiva -- antes el
    # puntaje agregado alcanzaba "Saludable" igual, porque una pérdida neta
    # pesaba lo mismo que cualquier otra señal floja. Perder dinero debe
    # impedir "Saludable" sin importar cuántas otras señales sean positivas.
    info = full_info(profitMargins=-0.20, returnOnEquity=-0.10, revenueGrowth=0.25,
                      debtToEquity=49.0, currentRatio=1.6)
    with patch.object(fundamentals, "_fetch_info", return_value=info):
        result = fundamentals.analyze("INTC")
    health = result["semaphores"]["health"]
    assert health["level"] == "yellow"
    assert health["label"] == "Mixto"
    assert "pérdidas netas" in health["detail"]


def test_analyze_insufficient_data_for_health():
    info = {"quoteType": "EQUITY", "trailingPE": 20.0}
    with patch.object(fundamentals, "_fetch_info", return_value=info):
        result = fundamentals.analyze("THIN")
    assert result["semaphores"]["health"]["level"] == "none"


def test_analyze_error_propagates_as_field():
    with patch.object(fundamentals, "_fetch_info", side_effect=fundamentals.FundamentalsError("sin datos")):
        result = fundamentals.analyze("XXXX")
    assert result["error"] == "sin datos"


def test_cache_avoids_second_fetch():
    with patch.object(fundamentals, "_fetch_info", return_value=full_info()) as mock:
        fundamentals.analyze("AAPL")
        fundamentals.analyze("AAPL")
        assert mock.call_count == 1
        fundamentals.analyze("AAPL", force=True)
        assert mock.call_count == 2
