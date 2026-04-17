"""AwesomeAPI service — FX rates against BRL (free, no key required)."""

import streamlit as st
from utils import CACHE_TTL
from utils.http import get_json
from utils.logger import get_logger

_log = get_logger(__name__)

_BASE = "https://economia.awesomeapi.com.br/last"

# Pairs: {label: awesome_pair_code}
FX_PAIRS = {
    "Dólar (USD)":   "USD-BRL",
    "Euro (EUR)":    "EUR-BRL",
    "Libra (GBP)":   "GBP-BRL",
    "Franco SUI":    "CHF-BRL",
    "Iene (JPY)":    "JPY-BRL",
    "Dólar CAN":     "CAD-BRL",
    "Dólar AUS":     "AUD-BRL",
    "Yuan (CNY)":    "CNY-BRL",
    "Peso ARG":      "ARS-BRL",
    "BRL → ARS":     "BRL-ARS",
    "BRL → PYG":     "BRL-PYG",
    "BRL → UYU":     "BRL-UYU",
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
        data = get_json(f"{_BASE}/{joined}", timeout=15, retries=2)
        if data is None:
            return {p: {"error": True} for p in pairs}
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
        _log.exception("AwesomeAPI parse falhou: %s", e)
        return {p: {"error": True, "msg": str(e)} for p in pairs}
