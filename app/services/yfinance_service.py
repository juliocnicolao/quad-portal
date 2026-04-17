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
    """Returns latest price, previous close, and % change for a single ticker.
    Uses history() instead of fast_info for better reliability on cloud hosts."""
    try:
        # history() é mais estável no Streamlit Cloud que fast_info
        df = yf.download(ticker, period="5d", interval="1d",
                         progress=False, auto_adjust=False, threads=False)
        df = _flatten(df)
        if df.empty or "Close" not in df.columns:
            return {"ticker": ticker, "price": None, "prev_close": None,
                    "change_pct": None, "error": True, "msg": "empty"}
        closes = df["Close"].dropna()
        if closes.empty:
            return {"ticker": ticker, "price": None, "error": True, "msg": "no closes"}
        price = float(closes.iloc[-1])
        prev  = float(closes.iloc[-2]) if len(closes) >= 2 else price
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


@st.cache_data(ttl=CACHE_TTL, persist="disk")
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


@st.cache_data(ttl=CACHE_TTL, persist="disk")
def get_detail(ticker: str) -> dict:
    """Richer info for the detail panel — uses 1y history for stability on cloud."""
    try:
        # Usar 1y history para calcular high/low 52w de forma confiável
        df = yf.download(ticker, period="1y", interval="1d",
                         progress=False, auto_adjust=False, threads=False)
        df = _flatten(df)
        if df.empty or "Close" not in df.columns:
            return {"error": True, "msg": "no data"}
        closes = df["Close"].dropna()
        highs  = df["High"].dropna() if "High" in df.columns else closes
        lows   = df["Low"].dropna()  if "Low"  in df.columns else closes
        vols   = df["Volume"].dropna() if "Volume" in df.columns else pd.Series([0])

        if closes.empty:
            return {"error": True, "msg": "no closes"}

        price = float(closes.iloc[-1])
        prev  = float(closes.iloc[-2]) if len(closes) >= 2 else price
        change_pct = ((price - prev) / prev * 100) if prev else 0.0

        # Tentar buscar nome/moeda via info (pode falhar no cloud — tratado)
        name, currency, market_cap = ticker, "USD", None
        try:
            info = yf.Ticker(ticker).info or {}
            name = info.get("longName") or info.get("shortName", ticker)
            currency = info.get("currency", "USD")
            market_cap = info.get("marketCap")
        except Exception:
            pass

        return {
            "name":        name,
            "price":       price,
            "change_pct":  change_pct,
            "high_52w":    float(highs.max()),
            "low_52w":     float(lows.min()),
            "volume":      float(vols.tail(60).mean()) if len(vols) else 0,
            "market_cap":  market_cap,
            "currency":    currency,
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
