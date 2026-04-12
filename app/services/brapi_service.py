"""Brapi.dev service — Ibovespa and Brazilian equity tickers (15min delay, free tier)."""

import streamlit as st
import requests
from app.utils import CACHE_TTL

_BASE = "https://brapi.dev/api"


@st.cache_data(ttl=CACHE_TTL)
def get_quote(ticker: str) -> dict:
    """Single BR ticker quote from Brapi."""
    try:
        r = requests.get(f"{_BASE}/quote/{ticker}", timeout=8)
        r.raise_for_status()
        data = r.json()["results"][0]
        price      = data.get("regularMarketPrice")
        prev       = data.get("regularMarketPreviousClose")
        change_pct = data.get("regularMarketChangePercent")
        return {
            "ticker":     ticker,
            "name":       data.get("longName", ticker),
            "price":      price,
            "prev_close": prev,
            "change_pct": change_pct,
            "error":      False,
        }
    except Exception as e:
        return {"ticker": ticker, "price": None, "prev_close": None,
                "change_pct": None, "error": True, "msg": str(e)}


@st.cache_data(ttl=CACHE_TTL)
def get_quotes(tickers: list[str]) -> dict[str, dict]:
    """Bulk BR quotes. Returns {ticker: quote_dict}."""
    joined = ",".join(tickers)
    try:
        r = requests.get(f"{_BASE}/quote/{joined}", timeout=10)
        r.raise_for_status()
        results = r.json().get("results", [])
        out = {}
        for data in results:
            t = data.get("symbol", "")
            out[t] = {
                "ticker":     t,
                "name":       data.get("longName", t),
                "price":      data.get("regularMarketPrice"),
                "prev_close": data.get("regularMarketPreviousClose"),
                "change_pct": data.get("regularMarketChangePercent"),
                "error":      False,
            }
        return out
    except Exception as e:
        return {t: {"ticker": t, "price": None, "change_pct": None,
                    "error": True, "msg": str(e)} for t in tickers}


@st.cache_data(ttl=CACHE_TTL)
def get_ibov_components() -> list[dict]:
    """Top Ibovespa movers (gainers + losers) via Brapi."""
    try:
        r = requests.get(f"{_BASE}/quote/list?sortBy=change&limit=10", timeout=10)
        r.raise_for_status()
        return r.json().get("stocks", [])
    except Exception:
        return []


# ── Default BR tickers to track ───────────────────────────────────────────────

BR_TICKERS = [
    "PETR4", "VALE3", "ITUB4", "BBDC4", "B3SA3",
    "ABEV3", "WEGE3", "RENT3", "MGLU3", "VIIA3",
]
