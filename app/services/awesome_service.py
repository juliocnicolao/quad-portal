"""AwesomeAPI service — FX rates against BRL (free, no key required)."""

import streamlit as st
import requests
from utils import CACHE_TTL

_BASE = "https://economia.awesomeapi.com.br/last"

# Pairs: {label: awesome_pair_code}
FX_PAIRS = {
    "Dólar (USD)":  "USD-BRL",
    "Euro (EUR)":   "EUR-BRL",
    "Libra (GBP)":  "GBP-BRL",
    "Peso ARG":     "ARS-BRL",
    "Franco SUI":   "CHF-BRL",
    "Iene (JPY)":   "JPY-BRL",
    "Yuan (CNY)":   "CNY-BRL",
}


@st.cache_data(ttl=CACHE_TTL)
def get_fx(pairs: list[str] | None = None) -> dict[str, dict]:
    """
    Fetch FX rates. `pairs` is a list of AwesomeAPI pair codes,
    defaults to all FX_PAIRS values.
    Returns {pair_code: {bid, ask, pct_change, error}}.
    """
    if pairs is None:
        pairs = list(FX_PAIRS.values())

    joined = ",".join(pairs)
    try:
        r = requests.get(f"{_BASE}/{joined}", timeout=15)
        r.raise_for_status()
        data = r.json()
        out = {}
        for code, v in data.items():
            try:
                bid        = float(v["bid"])
                ask        = float(v["ask"])
                pct_change = float(v.get("pctChange", 0))
                out[v["code"] + "-" + v["codein"]] = {
                    "bid":        bid,
                    "ask":        ask,
                    "mid":        (bid + ask) / 2,
                    "change_pct": pct_change,
                    "name":       v.get("name", code),
                    "error":      False,
                }
            except Exception:
                out[code] = {"error": True}
        return out
    except Exception as e:
        return {p: {"error": True, "msg": str(e)} for p in pairs}
