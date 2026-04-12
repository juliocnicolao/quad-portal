"""FRED service — US Treasuries yield curve and macro indicators."""

import streamlit as st
import pandas as pd
from fredapi import Fred
from utils import FRED_API_KEY, CACHE_TTL

_fred = Fred(api_key=FRED_API_KEY)

# Treasury yield series IDs
TREASURY_SERIES = {
    "3 meses":  "DGS3MO",
    "6 meses":  "DGS6MO",
    "1 ano":    "DGS1",
    "2 anos":   "DGS2",
    "5 anos":   "DGS5",
    "10 anos":  "DGS10",
    "20 anos":  "DGS20",
    "30 anos":  "DGS30",
}

US_MACRO_SERIES = {
    "fed_funds":     "FEDFUNDS",   # Fed Funds Rate
    "cpi_yoy":       "CPIAUCSL",   # CPI (level — calc YoY manually)
    "unemployment":  "UNRATE",     # US Unemployment
    "gdp_growth":    "A191RL1Q225SBEA",  # Real GDP growth QoQ
}


@st.cache_data(ttl=CACHE_TTL)
def get_treasury_curve() -> pd.DataFrame:
    """
    Returns latest Treasury yield curve as DataFrame
    with columns [maturity, yield_pct].
    """
    rows = []
    for label, series_id in TREASURY_SERIES.items():
        try:
            s = _fred.get_series(series_id, observation_start="2020-01-01")
            latest = float(s.dropna().iloc[-1])
            rows.append({"maturidade": label, "yield_pct": latest})
        except Exception:
            rows.append({"maturidade": label, "yield_pct": None})
    return pd.DataFrame(rows)


@st.cache_data(ttl=CACHE_TTL)
def get_treasury_history(series_id: str = "DGS10", years: int = 3) -> pd.DataFrame:
    """Historical yield for a single Treasury series."""
    try:
        start = pd.Timestamp.today() - pd.DateOffset(years=years)
        s = _fred.get_series(series_id, observation_start=start.strftime("%Y-%m-%d"))
        df = s.dropna().reset_index()
        df.columns = ["data", "yield_pct"]
        return df
    except Exception:
        return pd.DataFrame()


@st.cache_data(ttl=CACHE_TTL)
def get_latest_value(series_id: str) -> float | None:
    """Returns the most recent value of any FRED series."""
    try:
        s = _fred.get_series(series_id)
        return float(s.dropna().iloc[-1])
    except Exception:
        return None


@st.cache_data(ttl=CACHE_TTL)
def get_fed_funds() -> dict:
    val = get_latest_value(US_MACRO_SERIES["fed_funds"])
    return {"value": val, "label": "Fed Funds Rate", "unit": "% a.a."}


@st.cache_data(ttl=CACHE_TTL)
def get_us_unemployment() -> dict:
    val = get_latest_value(US_MACRO_SERIES["unemployment"])
    return {"value": val, "label": "Desemprego EUA", "unit": "%"}


@st.cache_data(ttl=CACHE_TTL)
def get_spread_10_2() -> dict:
    """10y - 2y spread (inversão da curva)."""
    try:
        s10 = _fred.get_series("DGS10").dropna().iloc[-1]
        s2  = _fred.get_series("DGS2").dropna().iloc[-1]
        spread = float(s10) - float(s2)
        return {"value": spread, "label": "Spread 10y-2y", "unit": "p.p."}
    except Exception:
        return {"value": None, "label": "Spread 10y-2y", "unit": "p.p."}
