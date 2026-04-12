"""BCB SGS service — Selic, IPCA, CDI, PIB, Desemprego and DI curve proxy."""

import streamlit as st
import requests
import pandas as pd
from utils import CACHE_TTL

_SGS = "https://api.bcb.gov.br/dados/serie/bcdata.sgs.{code}/dados/ultimos/{n}?formato=json"
_ANBIMA_CURVE = "https://www.anbima.com.br/informacoes/merc-sec/arqs/ms{date}.txt"

# BCB SGS series codes
SGS_CODES = {
    "selic_meta":    432,   # Taxa Selic meta (% a.a.)
    "selic_diaria":  11,    # Taxa Selic diária
    "cdi_diario":    12,    # CDI diário
    "ipca_mensal":   433,   # IPCA mensal (%)
    "ipca_12m":      13522, # IPCA acumulado 12 meses
    "igpm_mensal":   189,   # IGP-M mensal
    "pib_trimestral":4380,  # PIB trimestral (var. %)
    "desemprego":    24369, # Taxa desemprego PNAD
    "cambio_ptax":   1,     # PTAX dólar (venda)
    "reservas_int":  13621, # Reservas internacionais (US$ mi)
}


@st.cache_data(ttl=CACHE_TTL)
def get_serie(code: int, n: int = 1) -> list[dict]:
    """Fetch last `n` observations from BCB SGS. Returns list of {data, valor}."""
    try:
        r = requests.get(_SGS.format(code=code, n=n), timeout=10)
        r.raise_for_status()
        return r.json()
    except Exception:
        return []


@st.cache_data(ttl=CACHE_TTL)
def get_latest(code: int) -> float | None:
    """Returns the latest float value for a SGS series."""
    data = get_serie(code, n=1)
    if data:
        try:
            return float(data[-1]["valor"].replace(",", "."))
        except Exception:
            return None
    return None


@st.cache_data(ttl=CACHE_TTL)
def get_selic() -> dict:
    val = get_latest(SGS_CODES["selic_meta"])
    return {"value": val, "label": "Selic Meta", "unit": "% a.a."}


@st.cache_data(ttl=CACHE_TTL)
def get_ipca_12m() -> dict:
    val = get_latest(SGS_CODES["ipca_12m"])
    return {"value": val, "label": "IPCA 12m", "unit": "%"}


@st.cache_data(ttl=CACHE_TTL)
def get_desemprego() -> dict:
    val = get_latest(SGS_CODES["desemprego"])
    return {"value": val, "label": "Desemprego", "unit": "%"}


@st.cache_data(ttl=CACHE_TTL)
def get_ipca_history(n: int = 24) -> pd.DataFrame:
    """Returns last `n` months of IPCA as DataFrame with columns [data, valor]."""
    try:
        raw = get_serie(SGS_CODES["ipca_mensal"], n=n)
        if not raw:
            return pd.DataFrame()
        df = pd.DataFrame(raw)
        df["data"] = pd.to_datetime(df["data"], format="%d/%m/%Y")
        # BCB may return valor as string ("0,56") or float (0.56) — handle both
        df["valor"] = pd.to_numeric(
            df["valor"].astype(str).str.replace(",", "."), errors="coerce"
        )
        return df.dropna(subset=["valor"]).sort_values("data").reset_index(drop=True)
    except Exception:
        return pd.DataFrame()


@st.cache_data(ttl=CACHE_TTL)
def get_di_curve_proxy() -> pd.DataFrame:
    """
    DI curve proxy via yfinance futures (fallback if ANBIMA unavailable).
    Returns DataFrame with columns [vencimento, taxa].
    """
    # Approximation using DI1 contracts available on Yahoo Finance
    di_tickers = {
        "DI Jan/26": "DIF26.SA",
        "DI Jan/27": "DIF27.SA",
        "DI Jan/28": "DIF28.SA",
        "DI Jan/29": "DIF29.SA",
        "DI Jan/30": "DIF30.SA",
    }
    try:
        import yfinance as yf
        rows = []
        for label, ticker in di_tickers.items():
            info = yf.Ticker(ticker).fast_info
            price = info.last_price
            if price:
                # DI futures quote as PU (100k base), convert to rate
                taxa = (100_000 / price - 1) * 100
                rows.append({"vencimento": label, "taxa": round(taxa, 2)})
        return pd.DataFrame(rows)
    except Exception:
        return pd.DataFrame()
