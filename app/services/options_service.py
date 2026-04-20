"""Options service — fetch option chain via yfinance.

Fornece option chains e metricas agregadas (P/C ratio, IV avg) para ativos
americanos com chain disponivel. Isolado de analytics: funcoes aqui fazem
apenas I/O + normalizacao, nada de matematica financeira.
"""

from __future__ import annotations

import datetime as _dt
from typing import Any

import pandas as pd
import streamlit as st
import yfinance as yf

from utils import CACHE_TTL


def _days_to(expiry: str) -> int:
    """Dias corridos ate a data 'YYYY-MM-DD'. Minimo 1 (evita /0 em BS)."""
    try:
        d = _dt.datetime.strptime(expiry, "%Y-%m-%d").date()
        delta = (d - _dt.date.today()).days
        return max(delta, 1)
    except Exception:
        return 1


def _normalize_leg(df: pd.DataFrame, expiry: str) -> pd.DataFrame:
    """Padroniza colunas e filtra linhas invalidas.

    Mantem apenas colunas [strike, openInterest, volume, impliedVolatility,
    lastPrice, bid, ask, daysToExpiry, expiry].
    """
    if df is None or df.empty:
        return pd.DataFrame()
    keep = ["strike", "openInterest", "volume", "impliedVolatility",
            "lastPrice", "bid", "ask"]
    out = df.copy()
    for c in keep:
        if c not in out.columns:
            out[c] = 0.0
    out = out[keep].copy()
    out["openInterest"]      = pd.to_numeric(out["openInterest"], errors="coerce").fillna(0)
    out["volume"]            = pd.to_numeric(out["volume"], errors="coerce").fillna(0)
    out["impliedVolatility"] = pd.to_numeric(out["impliedVolatility"], errors="coerce").fillna(0)
    out["strike"]            = pd.to_numeric(out["strike"], errors="coerce")
    out = out.dropna(subset=["strike"])
    out["daysToExpiry"] = _days_to(expiry)
    out["expiry"]       = expiry
    return out


@st.cache_data(ttl=CACHE_TTL)
def get_expiries(ticker: str) -> list[str]:
    """Retorna lista de vencimentos disponiveis (strings YYYY-MM-DD)."""
    try:
        tk = yf.Ticker(ticker)
        exps = list(tk.options or [])
        return exps
    except Exception:
        return []


@st.cache_data(ttl=CACHE_TTL)
def get_chain(ticker: str, max_expiries: int = 6) -> dict[str, Any]:
    """Busca option chain agregada para os proximos N vencimentos.

    Returns:
        dict com chaves:
            - available (bool): se ha chain
            - expiries (list[str]): vencimentos carregados
            - calls (DataFrame): calls agregadas (todas as expiries)
            - puts  (DataFrame): puts agregadas
            - pc_oi   (float): Put/Call ratio por open interest
            - pc_vol  (float): Put/Call ratio por volume
            - iv_avg_calls (float), iv_avg_puts (float), iv_avg (float)
            - error (str | None)
    """
    empty: dict[str, Any] = {
        "available": False, "expiries": [],
        "calls": pd.DataFrame(), "puts": pd.DataFrame(),
        "pc_oi": 0.0, "pc_vol": 0.0,
        "iv_avg_calls": 0.0, "iv_avg_puts": 0.0, "iv_avg": 0.0,
        "error": None,
    }

    try:
        tk = yf.Ticker(ticker)
        exps = list(tk.options or [])
    except Exception as e:
        return {**empty, "error": f"Falha ao consultar vencimentos: {e}"}

    if not exps:
        return {**empty, "error": "Sem vencimentos disponiveis"}

    exps = exps[:max_expiries]
    calls_all: list[pd.DataFrame] = []
    puts_all:  list[pd.DataFrame] = []

    for exp in exps:
        try:
            oc = tk.option_chain(exp)
        except Exception:
            continue
        calls_all.append(_normalize_leg(oc.calls, exp))
        puts_all.append( _normalize_leg(oc.puts,  exp))

    calls = pd.concat(calls_all, ignore_index=True) if calls_all else pd.DataFrame()
    puts  = pd.concat(puts_all,  ignore_index=True) if puts_all  else pd.DataFrame()

    if calls.empty and puts.empty:
        return {**empty, "expiries": exps,
                "error": "Chain retornou vazio para todas as expiries"}

    oi_calls = float(calls["openInterest"].sum()) if not calls.empty else 0.0
    oi_puts  = float(puts["openInterest"].sum())  if not puts.empty  else 0.0
    vol_calls = float(calls["volume"].sum()) if not calls.empty else 0.0
    vol_puts  = float(puts["volume"].sum())  if not puts.empty  else 0.0

    pc_oi  = (oi_puts / oi_calls) if oi_calls > 0 else 0.0
    pc_vol = (vol_puts / vol_calls) if vol_calls > 0 else 0.0

    # IV medio ponderado por OI (mais representativo que simples mean)
    def _wavg_iv(df: pd.DataFrame) -> float:
        if df.empty: return 0.0
        w = df["openInterest"].to_numpy(dtype=float)
        iv = df["impliedVolatility"].to_numpy(dtype=float)
        mask = (w > 0) & (iv > 0)
        if not mask.any():
            iv_only = iv[iv > 0]
            return float(iv_only.mean()) if iv_only.size else 0.0
        return float((iv[mask] * w[mask]).sum() / w[mask].sum())

    iv_c = _wavg_iv(calls)
    iv_p = _wavg_iv(puts)
    iv_avg = ((iv_c + iv_p) / 2) if (iv_c and iv_p) else (iv_c or iv_p)

    return {
        "available": True,
        "expiries":   exps,
        "calls":      calls,
        "puts":       puts,
        "pc_oi":      pc_oi,
        "pc_vol":     pc_vol,
        "iv_avg_calls": iv_c,
        "iv_avg_puts":  iv_p,
        "iv_avg":     iv_avg,
        "error":      None,
    }
