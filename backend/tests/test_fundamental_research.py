from app.fundamental_research import build, fetch_annual


def fixture():
    income, balance, cash = {}, {}, {}
    for year in range(2019, 2025):
        date = f"{year}-12-31"
        income[date] = {"Total Revenue": 100 * 1.1 ** (year-2019), "Net Income": 20,
                        "EBIT": 30, "Operating Income": 30, "EBITDA": 40,
                        "Gross Profit": 60, "Interest Expense": 5,
                        "Tax Provision": 5, "Pretax Income": 25, "Cost Of Revenue": 40}
        balance[date] = {"Total Debt": 80, "Stockholders Equity": 120,
                         "Cash And Cash Equivalents": 20, "Inventory": 10,
                         "Accounts Receivable": 10, "Accounts Payable": 5}
        cash[date] = {"Operating Cash Flow": 30, "Capital Expenditure": -10,
                     "Common Stock Dividend Paid": -5, "Repurchase Of Capital Stock": -8}
    return {"_annual": {"income_stmt":income,"balance_sheet":balance,"cashflow":cash},
            "sector":"Technology", "currency":"USD", "financialCurrency":"USD",
            "marketCap":400, "currentPrice":40,"trailingEps":2,"forwardPE":15}


def metrics(result):
    return {m["key"]:m for b in result["blocks"] for m in b["metrics"]}


def test_aligned_annual_calculations_and_dates():
    import pytest
    result=build(fixture(),"TEST")
    m=metrics(result)
    assert m["roic"]["value"] == pytest.approx(24/180)
    assert m["interestCoverage"]["value"] == 6
    assert m["debtEbitda"]["value"] == 1.5
    assert m["priceFcf"]["value"] == 20
    assert m["fcfYield"]["value"] == .05
    assert m["fcfPayout"]["value"] == .25
    assert m["conversion"]["value"] == 1
    assert m["cagr5"]["value"] == pytest.approx(.1, abs=.0001)
    assert m["roic"]["period"] == "2024-12-31"
    assert all(m["explanation"] and m["source"].startswith("https://") for m in m.values())


def test_currency_mismatch_blocks_price_to_cashflow_and_eps_model():
    info=fixture();info["financialCurrency"]="EUR"
    result=build(info,"TEST");m=metrics(result)
    assert m["priceFcf"]["value"] is None
    assert m["fcfYield"]["value"] is None
    assert result["scenario"]["eps"] is None


def test_short_history_is_not_five_year_cagr():
    info=fixture();del info["_annual"]["income_stmt"]["2019-12-31"]
    assert metrics(build(info,"TEST"))["cagr5"]["value"] is None


def test_missing_capex_is_not_assumed_zero():
    info=fixture();del info["_annual"]["cashflow"]["2024-12-31"]["Capital Expenditure"]
    m=metrics(build(info,"TEST"))
    assert m["conversion"]["value"] is None
    assert m["priceFcf"]["value"] is None


def test_bank_does_not_get_generic_roic_or_debt_model():
    info=fixture();info["sector"]="Financial Services"
    result=build(info,"BANK");m=metrics(result)
    assert m["roic"]["condition"] == "No aplicable"
    assert m["debtEbitda"]["value"] is None
    assert not result["scenario"]["applicable"]


def test_fetch_missing_statements_and_invalid_denominators():
    assert fetch_annual(object()) == {"income_stmt":{},"balance_sheet":{},"cashflow":{}}
    info=fixture();info["_annual"]["income_stmt"]["2024-12-31"].update({"EBITDA":0,"Net Income":-5,"Interest Expense":0})
    m=metrics(build(info,"TEST"))
    for key in ("debtEbitda","conversion","interestCoverage"):
        assert m[key]["value"] is None


def test_no_mixing_dates_for_roic():
    info=fixture();del info["_annual"]["balance_sheet"]["2023-12-31"]
    assert metrics(build(info,"TEST"))["roic"]["value"] is None
