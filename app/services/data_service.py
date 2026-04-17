"""Unified data service with cascading fallbacks.

Centraliza a lógica de: yfinance → stooq para cotações/histórico,
brapi → yfinance → stooq para ativos brasileiros. Também carimba
cada resposta com `source` e `fetched_at` para diagnosticar em UI.
"""

from __future__ import annotations

import time
import pandas as pd
import streamlit as st

from services import yfinance_service as yf_svc
from services import stooq_service    as stooq
from services import brapi_service    as brapi


def _stamp(d: dict, source: str) -> dict:
    d = {**d}
    d["source"]     = source
    d["fetched_at"] = time.time()
    return d


# ── Quotes ───────────────────────────────────────────────────────────────────

def quote(ticker: str, *, br: bool = False) -> dict:
    """Cascade: [brapi (if br)] → yfinance → stooq.

    Retorna sempre dict com chaves: ticker, price, change_pct, error, source.
    """
    if br:
        q = brapi.get_quote(ticker)
        if not q.get("error") and q.get("price") is not None:
            return _stamp(q, "brapi")

    q = yf_svc.get_quote(ticker)
    if not q.get("error") and q.get("price") is not None:
        return _stamp(q, "yfinance")

    q = stooq.get_quote(ticker)
    if not q.get("error") and q.get("price") is not None:
        return _stamp(q, "stooq")

    return _stamp(
        {"ticker": ticker, "price": None, "change_pct": None, "error": True,
         "msg": "todas as fontes falharam"},
        "none",
    )


def quotes(tickers: list[str], *, br: bool = False) -> dict[str, dict]:
    """Bulk quotes com cascade por ticker."""
    return {t: quote(t, br=br) for t in tickers}


# ── History ──────────────────────────────────────────────────────────────────

def history(ticker: str, period: str = "6mo") -> pd.DataFrame:
    """Cascade yfinance → stooq para séries históricas OHLCV."""
    df = yf_svc.get_history(ticker, period=period)
    if df is not None and not df.empty:
        df.attrs["source"] = "yfinance"
        return df
    df = stooq.get_history(ticker, period=period)
    if df is not None and not df.empty:
        df.attrs["source"] = "stooq"
        return df
    empty = pd.DataFrame()
    empty.attrs["source"] = "none"
    return empty


# ── Detail (para o painel de análise) ────────────────────────────────────────

def detail(ticker: str) -> dict:
    """Cascade de detalhe: yfinance → (stooq-derived a partir de 1y history)."""
    d = yf_svc.get_detail(ticker)
    if not d.get("error") and d.get("price"):
        return _stamp(d, "yfinance")

    hist = stooq.get_history(ticker, period="1y")
    if hist.empty or "Close" not in hist.columns:
        return _stamp({"error": True, "msg": "sem dados"}, "none")

    closes = hist["Close"].dropna()
    if closes.empty:
        return _stamp({"error": True, "msg": "sem fechamentos"}, "none")

    price = float(closes.iloc[-1])
    prev  = float(closes.iloc[-2]) if len(closes) >= 2 else price
    change_pct = ((price - prev) / prev * 100) if prev else 0.0
    highs = hist["High"].dropna() if "High" in hist.columns else closes
    lows  = hist["Low"].dropna()  if "Low"  in hist.columns else closes
    vols  = hist["Volume"].dropna() if "Volume" in hist.columns else None

    return _stamp({
        "name":       ticker,
        "price":      price,
        "change_pct": change_pct,
        "high_52w":   float(highs.max()),
        "low_52w":    float(lows.min()),
        "volume":     float(vols.tail(60).mean()) if vols is not None and len(vols) else 0,
        "market_cap": None,
        "currency":   "USD",
        "error":      False,
    }, "stooq")
