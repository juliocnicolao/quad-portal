"""yfinance service — US indices, commodities, crypto, BR tickers fallback."""

import streamlit as st
import yfinance as yf
import pandas as pd
from utils import CACHE_TTL


def _flatten(df: pd.DataFrame) -> pd.DataFrame:
    """Flatten MultiIndex columns returned by yfinance ≥ 0.2.x."""
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    return df


@st.cache_data(ttl=CACHE_TTL)
def get_quote(ticker: str) -> dict:
    """Returns latest price, previous close, and % change for a single ticker."""
    try:
        t = yf.Ticker(ticker)
        info = t.fast_info
        price = info.last_price
        prev  = info.previous_close
        change_pct = ((price - prev) / prev * 100) if prev else 0.0
        return {
            "ticker":     ticker,
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
    """Bulk quotes. Returns {ticker: quote_dict}."""
    return {t: get_quote(t) for t in tickers}


@st.cache_data(ttl=CACHE_TTL)
def get_history(ticker: str, period: str = "6mo", interval: str = "1d") -> pd.DataFrame:
    """OHLCV history for charting. period: 1mo 3mo 6mo 1y 5y."""
    try:
        df = yf.download(ticker, period=period, interval=interval,
                         progress=False, auto_adjust=True)
        df = _flatten(df)
        df.index = pd.to_datetime(df.index)
        # Remove timezone so Plotly renders cleanly
        if df.index.tz is not None:
            df.index = df.index.tz_localize(None)
        return df
    except Exception:
        return pd.DataFrame()


@st.cache_data(ttl=CACHE_TTL)
def get_detail(ticker: str) -> dict:
    """Richer info for the detail panel: 52w high/low, volume, name."""
    try:
        t    = yf.Ticker(ticker)
        info = t.info
        fi   = t.fast_info
        return {
            "name":        info.get("longName") or info.get("shortName", ticker),
            "price":       fi.last_price,
            "change_pct":  ((fi.last_price - fi.previous_close) / fi.previous_close * 100)
                           if fi.previous_close else 0.0,
            "high_52w":    fi.year_high,
            "low_52w":     fi.year_low,
            "volume":      fi.three_month_average_volume,
            "market_cap":  info.get("marketCap"),
            "currency":    info.get("currency", "USD"),
            "error":       False,
        }
    except Exception as e:
        return {"error": True, "msg": str(e)}


# ── Ticker maps ───────────────────────────────────────────────────────────────

US_INDICES = {
    "S&P 500":       "^GSPC",
    "Nasdaq":        "^IXIC",
    "Dow Jones":     "^DJI",
    "Euro Stoxx 50": "^STOXX50E",
    "Nikkei 225":    "^N225",
    "FTSE 100":      "^FTSE",
    "DAX":           "^GDAXI",
}

COMMODITIES = {
    "Petróleo WTI":  "CL=F",
    "Petróleo Brent":"BZ=F",
    "Ouro":          "GC=F",
    "Prata":         "SI=F",
    "Soja":          "ZS=F",
    "Milho":         "ZC=F",
    "Trigo":         "ZW=F",
    "Boi Gordo":     "LE=F",
}

CRYPTO = {
    "Bitcoin":  "BTC-USD",
    "Ethereum": "ETH-USD",
    "BNB":      "BNB-USD",
    "Solana":   "SOL-USD",
}

BR_TICKERS_YF = {
    "Ibovespa": "^BVSP",
    "PETR4":    "PETR4.SA",
    "VALE3":    "VALE3.SA",
    "ITUB4":    "ITUB4.SA",
}

DXY = {"DXY (Dólar Index)": "DX-Y.NYB"}
