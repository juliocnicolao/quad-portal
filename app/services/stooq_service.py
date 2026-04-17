"""Stooq service — fallback for when yfinance is blocked on cloud hosts.
Stooq provides free CSV quotes and historical data, very reliable on cloud."""

import streamlit as st
import pandas as pd
import requests
from io import StringIO
from utils import CACHE_TTL


# Map yfinance-style tickers → Stooq symbols
STOOQ_MAP = {
    "^BVSP":   "^bvp",     # Ibovespa
    "^GSPC":   "^spx",     # S&P 500
    "^IXIC":   "^ndq",     # Nasdaq
    "^DJI":    "^dji",     # Dow Jones
    "^FTSE":   "^ftm",     # FTSE 100
    "^GDAXI":  "^dax",     # DAX
    "^N225":   "^nkx",     # Nikkei 225
    "USDBRL=X":"usdbrl",   # USD/BRL
    "CL=F":    "cl.f",     # WTI
    "BZ=F":    "cb.f",     # Brent
    "GC=F":    "gc.f",     # Gold
    "SI=F":    "si.f",     # Silver
    "BTC-USD": "btcusd",
    "ETH-USD": "ethusd",
}


def _to_stooq(ticker: str) -> str:
    """Convert yfinance ticker to Stooq symbol."""
    if ticker in STOOQ_MAP:
        return STOOQ_MAP[ticker]
    # Brazilian stocks: PETR4.SA → petr4.sa
    if ticker.endswith(".SA"):
        return ticker.lower()
    return ticker.lower()


@st.cache_data(ttl=CACHE_TTL)
def get_quote(ticker: str) -> dict:
    """Fetch last quote from Stooq via CSV. Returns same schema as yfinance_service."""
    symbol = _to_stooq(ticker)
    url = f"https://stooq.com/q/l/?s={symbol}&f=sd2t2ohlcv&h&e=csv"
    try:
        r = requests.get(url, timeout=10,
                         headers={"User-Agent": "Mozilla/5.0"})
        r.raise_for_status()
        df = pd.read_csv(StringIO(r.text))
        if df.empty or "Close" not in df.columns:
            return {"ticker": ticker, "price": None, "error": True}
        row = df.iloc[0]
        close = row.get("Close")
        openp = row.get("Open")
        if close is None or pd.isna(close) or str(close).strip() == "N/D":
            return {"ticker": ticker, "price": None, "error": True}
        price = float(close)
        prev  = float(openp) if openp is not None and not pd.isna(openp) else price
        change_pct = ((price - prev) / prev * 100) if prev else 0.0
        return {
            "ticker":     ticker,
            "price":      price,
            "prev_close": prev,
            "change_pct": change_pct,
            "error":      False,
        }
    except Exception as e:
        return {"ticker": ticker, "price": None, "error": True, "msg": str(e)}


@st.cache_data(ttl=CACHE_TTL, persist="disk")
def get_history(ticker: str, period: str = "6mo") -> pd.DataFrame:
    """Fetch historical daily data from Stooq.
    period: "1mo", "3mo", "6mo", "1y", "2y", "5y" """
    symbol = _to_stooq(ticker)
    # Stooq aceita periodo via d (daily). Vamos puxar tudo e filtrar.
    url = f"https://stooq.com/q/d/l/?s={symbol}&i=d"
    try:
        r = requests.get(url, timeout=15,
                         headers={"User-Agent": "Mozilla/5.0"})
        r.raise_for_status()
        df = pd.read_csv(StringIO(r.text))
        if df.empty or "Date" not in df.columns:
            return pd.DataFrame()
        df["Date"] = pd.to_datetime(df["Date"])
        df = df.set_index("Date").sort_index()

        # Filtrar por período
        days = {"1mo": 30, "3mo": 90, "6mo": 180, "1y": 365,
                "2y": 730, "5y": 1825, "10y": 3650}.get(period, 180)
        cutoff = df.index.max() - pd.Timedelta(days=days)
        df = df[df.index >= cutoff]
        return df
    except Exception:
        return pd.DataFrame()
