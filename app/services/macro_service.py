"""
Macro service — country fundamentals.
Sources: IMF DataMapper (GDP, Inflation, Gross Debt) + FRED + BCB (rates).
Net Debt/GDP: IMF WEO 2024 Oct — updated annually, stored as static fallback.
"""

import math
import datetime
import streamlit as st
import requests
import pandas as pd
from fredapi import Fred
from app.utils import FRED_API_KEY, CACHE_TTL

_fred = Fred(api_key=FRED_API_KEY)
_IMF  = "https://www.imf.org/external/datamapper/api/v1/{indicator}/{countries}"

# Cap IMF data: GDP/Debt → previous year (actuals), Inflation → current year
_CY       = datetime.date.today().year
_MAX_YEAR      = str(_CY)       # inflation — current year estimate
_MAX_YEAR_GDP  = str(_CY - 1)  # GDP/Debt   — previous year (actual data)

# ── Country registry ──────────────────────────────────────────────────────────
# infl_source:   "imf" | "fred_cpi" | "bcb_ipca"
# infl_override: hard-coded when IMF projections are unreliable (e.g. Argentina)
# rate_fallback: used when live API fails — update whenever central bank meets
COUNTRIES = {
    "🇺🇸 EUA":        {"imf": "USA", "fred_rate": "FEDFUNDS",         "rate_fallback": 4.33,  "infl_source": "fred_cpi"},
    "🇧🇷 Brasil":     {"imf": "BRA", "bcb_rate":  432,                "rate_fallback": 14.75, "infl_source": "bcb_ipca"},
    "🇬🇧 Inglaterra": {"imf": "GBR", "fred_rate": "IRSTCB01GBM156N",  "rate_fallback": 3.75},
    "🇩🇪 Alemanha":   {"imf": "DEU", "fred_rate": "ECBDFR",           "rate_fallback": 2.00},
    "🇮🇹 Itália":     {"imf": "ITA", "fred_rate": "ECBDFR",           "rate_fallback": 2.00},
    "🇦🇺 Austrália":  {"imf": "AUS", "fred_rate": "IRSTCB01AUM156N",  "rate_fallback": 4.10},
    "🇮🇳 Índia":      {"imf": "IND", "fred_rate": "IRSTCB01INM156N",  "rate_fallback": 5.25},
    "🇯🇵 Japão":      {"imf": "JPN", "fred_rate": "IRSTCB01JPM156N",  "rate_fallback": 0.75},
    "🇵🇾 Paraguai":   {"imf": "PRY", "manual_rate": 6.00},
    "🇦🇷 Argentina":  {"imf": "ARG", "manual_rate": 35.0,             "infl_override": 33.0},
}

# IMF WEO Oct/2024 — Net Debt (% of GDP). Updated annually.
NET_DEBT_WEO = {
    "USA": 97.7,  "BRA": 74.1,  "GBR": 83.3,
    "DEU": 44.0,  "ITA": 138.3, "AUS": 17.0,
    "IND": 82.7,  "JPN": 155.3, "PRY": 30.0, "ARG": 45.5,
}

_IMF_CODES = ",".join(c["imf"] for c in COUNTRIES.values())


@st.cache_data(ttl=CACHE_TTL * 8)   # 2 hours — annual data changes rarely
def _fetch_imf(indicator: str, max_year: str = _MAX_YEAR) -> dict[str, float]:
    """Fetch latest available value from IMF DataMapper for all countries.
    max_year caps which year is selected — use _MAX_YEAR_GDP for actuals,
    _MAX_YEAR for current-year estimates/projections.
    """
    try:
        url = _IMF.format(indicator=indicator, countries=_IMF_CODES)
        r   = requests.get(url, timeout=12)
        r.raise_for_status()
        raw = r.json().get("values", {}).get(indicator, {})
        out = {}
        for code, years in raw.items():
            if years:
                valid = {y: v for y, v in years.items() if y <= max_year and v is not None}
                if not valid:
                    valid = {y: v for y, v in years.items() if v is not None}
                if valid:
                    latest_year = sorted(valid.keys())[-1]
                    out[code] = {"value": float(valid[latest_year]), "year": latest_year}
        return out
    except Exception:
        return {}


@st.cache_data(ttl=CACHE_TTL * 4)   # 1 hour — CPI releases monthly
def _fetch_fred_cpi_yoy() -> float | None:
    """US CPI YoY % — FRED CPIAUCSL (real monthly data, not IMF projection)."""
    try:
        s = _fred.get_series("CPIAUCSL")
        yoy = s.pct_change(12) * 100
        val = float(yoy.dropna().iloc[-1])
        return None if math.isnan(val) else round(val, 1)
    except Exception:
        return None


@st.cache_data(ttl=CACHE_TTL * 4)   # 1 hour — BCB releases monthly
def _fetch_bcb_ipca_12m() -> float | None:
    """Brazil IPCA acumulado 12 meses — BCB série 13522."""
    try:
        r = requests.get(
            "https://api.bcb.gov.br/dados/serie/bcdata.sgs.13522"
            "/dados/ultimos/1?formato=json", timeout=8
        )
        val = r.json()[0]["valor"]
        result = float(str(val).replace(",", "."))
        return None if math.isnan(result) else result
    except Exception:
        return None


@st.cache_data(ttl=CACHE_TTL * 4)   # 1 hour — rates change monthly at most
def _fetch_fred_rate(series_id: str) -> float | None:
    try:
        s = _fred.get_series(series_id)
        val = float(s.dropna().iloc[-1])
        return None if math.isnan(val) else val
    except Exception:
        return None


@st.cache_data(ttl=CACHE_TTL)
def _fetch_bcb_rate(code: int) -> float | None:
    try:
        r = requests.get(
            f"https://api.bcb.gov.br/dados/serie/bcdata.sgs.{code}"
            "/dados/ultimos/1?formato=json", timeout=8
        )
        val = r.json()[0]["valor"]
        result = float(str(val).replace(",", "."))
        return None if math.isnan(result) else result
    except Exception:
        return None


@st.cache_data(ttl=CACHE_TTL * 4)
def get_all_fundamentals() -> pd.DataFrame:
    """
    Returns a DataFrame with one row per country and columns:
    País, PIB (USD bi), Inflação %, Dívida Bruta %, Dívida Líq. %, Juros %, Ano PIB
    """
    gdp_data    = _fetch_imf("NGDPD",        max_year=_MAX_YEAR_GDP)  # Billions USD — prefer actuals
    infl_data   = _fetch_imf("PCPIPCH",     max_year=_MAX_YEAR)      # CPI % — current year estimate
    gross_data  = _fetch_imf("GGXWDG_NGDP", max_year=_MAX_YEAR_GDP)  # Gross debt — prefer actuals

    # Live inflation overrides (real-time, beat IMF projections)
    _us_cpi   = _fetch_fred_cpi_yoy()
    _br_ipca  = _fetch_bcb_ipca_12m()

    rows = []
    for display, cfg in COUNTRIES.items():
        code = cfg["imf"]

        gdp   = gdp_data.get(code)
        gross = gross_data.get(code)
        net   = NET_DEBT_WEO.get(code)

        # Inflation priority: override → real-time API → IMF projection
        if "infl_override" in cfg:
            infl_val = cfg["infl_override"]
        else:
            infl_src = cfg.get("infl_source", "imf")
            if infl_src == "fred_cpi" and _us_cpi is not None:
                infl_val = _us_cpi
            elif infl_src == "bcb_ipca" and _br_ipca is not None:
                infl_val = _br_ipca
            else:
                raw = infl_data.get(code)
                infl_val = raw["value"] if raw else None

        # Interest rate — live fetch with fallback to known manual value
        if "fred_rate" in cfg:
            rate = _fetch_fred_rate(cfg["fred_rate"])
        elif "bcb_rate" in cfg:
            rate = _fetch_bcb_rate(cfg["bcb_rate"])
        else:
            rate = cfg.get("manual_rate")
        if rate is None and "rate_fallback" in cfg:
            rate = cfg["rate_fallback"]

        rows.append({
            "País":              display,
            "_imf":              code,
            "PIB (USD)":         gdp["value"] if gdp else None,
            "_pib_year":         gdp["year"]  if gdp else "—",
            "Inflação %":        infl_val,
            "Dívida Bruta/PIB":  gross["value"] if gross else None,
            "Dívida Líq./PIB":   net,
            "Taxa de Juros %":   rate,
        })

    return pd.DataFrame(rows)
