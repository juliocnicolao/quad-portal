"""
Macro service — country fundamentals.
Sources: IMF DataMapper (GDP, Inflation, Gross Debt) + FRED + BCB (rates).
Net Debt/GDP: IMF WEO 2024 Oct — updated annually, stored as static fallback.
"""

import math
import datetime
import streamlit as st
import pandas as pd
from utils import FRED_API_KEY, CACHE_TTL
from utils.http import get_json
from utils.logger import get_logger

_log = get_logger(__name__)

# Fred só é inicializado se houver chave (evita crash em ambiente sem secret)
if FRED_API_KEY:
    try:
        from fredapi import Fred
        _fred = Fred(api_key=FRED_API_KEY)
    except Exception as e:
        _log.warning("FRED API não inicializada: %s", e)
        _fred = None
else:
    _log.warning("FRED_API_KEY ausente — séries US degradadas")
    _fred = None
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

# IMF WEO Oct/2024 — GDP nominal (USD billions, actual 2024).
# Fallback quando API IMF DataMapper falha. Atualizar anualmente.
GDP_WEO = {
    "USA": 29167.8, "BRA":  2188.4, "GBR": 3587.5,
    "DEU":  4710.0, "ITA":  2376.5, "AUS": 1802.1,
    "IND":  3889.1, "JPN":  4070.1, "PRY":   45.7, "ARG": 633.2,
}
GDP_WEO_YEAR = "2024"

# IMF WEO Oct/2024 — Gross Debt (% of GDP, 2024 estimate).
GROSS_DEBT_WEO = {
    "USA": 121.0, "BRA":  87.6, "GBR": 101.8,
    "DEU":  62.7, "ITA": 136.9, "AUS":  49.3,
    "IND":  83.0, "JPN": 251.2, "PRY":  40.8, "ARG": 90.9,
}

# IMF WEO Oct/2024 — Inflation % (annual change, 2025 projection).
INFL_WEO = {
    "USA": 2.0, "BRA": 4.0, "GBR": 2.1,
    "DEU": 2.1, "ITA": 1.8, "AUS": 2.8,
    "IND": 4.4, "JPN": 2.0, "PRY": 3.8, "ARG": 62.7,
}

_IMF_CODES = ",".join(c["imf"] for c in COUNTRIES.values())


@st.cache_data(ttl=CACHE_TTL * 8, persist="disk")   # 2 hours — annual data changes rarely
def _fetch_imf(indicator: str, max_year: str = _MAX_YEAR) -> dict[str, float]:
    """Fetch latest available value from IMF DataMapper for all countries.
    max_year caps which year is selected — use _MAX_YEAR_GDP for actuals,
    _MAX_YEAR for current-year estimates/projections.
    """
    try:
        url = _IMF.format(indicator=indicator, countries=_IMF_CODES)
        payload = get_json(url, timeout=12, retries=2)
        if not payload:
            return {}
        raw = payload.get("values", {}).get(indicator, {})
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


@st.cache_data(ttl=CACHE_TTL * 4, persist="disk")   # 1 hour — CPI releases monthly
def _fetch_fred_cpi_yoy() -> float | None:
    """US CPI YoY % — tenta fredapi; fallback via HTTP direto FRED (sem depender fredapi)."""
    if _fred is not None:
        try:
            s = _fred.get_series("CPIAUCSL")
            yoy = s.pct_change(12) * 100
            val = float(yoy.dropna().iloc[-1])
            if not math.isnan(val):
                return round(val, 1)
        except Exception as e:
            _log.warning("fredapi CPI falhou: %s", e)

    # Fallback: FRED HTTP API direto (precisa da key)
    if not FRED_API_KEY:
        return None
    try:
        payload = get_json(
            "https://api.stlouisfed.org/fred/series/observations",
            params={"series_id": "CPIAUCSL", "api_key": FRED_API_KEY,
                    "file_type": "json", "sort_order": "desc", "limit": 13},
            timeout=10, retries=2,
        )
        if not payload:
            return None
        obs = [o for o in payload.get("observations", []) if o.get("value") not in (".", None)]
        if len(obs) < 13:
            return None
        latest = float(obs[0]["value"])
        year_ago = float(obs[12]["value"])
        if year_ago <= 0:
            return None
        yoy = (latest / year_ago - 1) * 100
        return round(yoy, 1)
    except Exception as e:
        _log.warning("FRED HTTP CPI falhou: %s", e)
        return None


@st.cache_data(ttl=CACHE_TTL * 4, persist="disk")
def _fetch_bcb_gross_debt() -> float | None:
    """Dívida Bruta Gov Geral BR % PIB — BCB série 13762 (DBGG)."""
    try:
        payload = get_json(
            "https://api.bcb.gov.br/dados/serie/bcdata.sgs.13762"
            "/dados/ultimos/1?formato=json", timeout=8, retries=2,
        )
        if not payload:
            return None
        val = float(str(payload[0]["valor"]).replace(",", "."))
        return None if math.isnan(val) else val
    except Exception as e:
        _log.warning("BCB Dívida Bruta falhou: %s", e)
        return None


@st.cache_data(ttl=CACHE_TTL * 4, persist="disk")   # 1 hour — BCB releases monthly
def _fetch_bcb_ipca_12m() -> float | None:
    """Brazil IPCA acumulado 12 meses — BCB série 13522."""
    try:
        payload = get_json(
            "https://api.bcb.gov.br/dados/serie/bcdata.sgs.13522"
            "/dados/ultimos/1?formato=json", timeout=8, retries=2,
        )
        if not payload:
            return None
        val = payload[0]["valor"]
        result = float(str(val).replace(",", "."))
        return None if math.isnan(result) else result
    except Exception as e:
        _log.warning("BCB IPCA 12m falhou: %s", e)
        return None


@st.cache_data(ttl=CACHE_TTL * 4, persist="disk")   # 1 hour — rates change monthly at most
def _fetch_fred_rate(series_id: str) -> float | None:
    if _fred is None:
        return None
    try:
        s = _fred.get_series(series_id)
        val = float(s.dropna().iloc[-1])
        return None if math.isnan(val) else val
    except Exception:
        return None


@st.cache_data(ttl=CACHE_TTL)
def _fetch_bcb_rate(code: int) -> float | None:
    try:
        payload = get_json(
            f"https://api.bcb.gov.br/dados/serie/bcdata.sgs.{code}"
            "/dados/ultimos/1?formato=json", timeout=8, retries=2,
        )
        if not payload:
            return None
        val = payload[0]["valor"]
        result = float(str(val).replace(",", "."))
        return None if math.isnan(result) else result
    except Exception as e:
        _log.warning("BCB rate %s falhou: %s", code, e)
        return None


@st.cache_data(ttl=CACHE_TTL * 4, persist="disk")
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
    _br_gross = _fetch_bcb_gross_debt()   # BCB DBGG atualizado

    rows = []
    for display, cfg in COUNTRIES.items():
        code = cfg["imf"]

        # GDP: IMF API → WEO fallback
        gdp = gdp_data.get(code)
        if not gdp and code in GDP_WEO:
            gdp = {"value": GDP_WEO[code], "year": GDP_WEO_YEAR}

        # Gross Debt: BCB live (Brasil) → IMF API → WEO fallback
        gross = gross_data.get(code)
        if code == "BRA" and _br_gross is not None:
            gross = {"value": _br_gross, "year": str(_CY)}
        elif not gross and code in GROSS_DEBT_WEO:
            gross = {"value": GROSS_DEBT_WEO[code], "year": "2024"}

        net = NET_DEBT_WEO.get(code)

        # Inflation priority: override → real-time API → IMF API → WEO fallback
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
                infl_val = raw["value"] if raw else INFL_WEO.get(code)

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
