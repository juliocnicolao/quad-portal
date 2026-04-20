"""IV History Service — IV Rank real com duas fontes.

Arquitetura em duas pernas:

1. **CBOE Vol Indices** (disponivel hoje, sem ramp-up):
   Para tickers com indice de volatilidade oficial da CBOE publicado via
   Yahoo Finance, o historico de IV implicita ja existe e e baixavel.

2. **Self-persisted ATM IV** (ramp-up ~60 pregoes):
   Para tickers sem vol index (single names, setoriais menores), um job
   diario (GitHub Action) grava em `data/iv_history.csv` o ATM IV de cada
   ticker da watchlist. Apos 60 pregoes acumulados, temos IV Rank confiavel.

API publica: `get_iv_rank(ticker, current_iv)`.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta
from typing import Any

import pandas as pd
import streamlit as st

from services import data_service as data
from services import options_analytics as oa
from utils import CACHE_TTL


# ── CBOE Vol Indices map ─────────────────────────────────────────────────────
#
# Para cada ticker, o indice CBOE que reflete a IV do subjacente.
# Tickers nao listados aqui caem no self-history CSV.
#
# Fonte: https://www.cboe.com/tradable_products/vix/ e produtos relacionados.
#
# Nota: ^VXEEM (Emerging Markets) e usado como proxy para EWZ/EEM pois e a
# melhor referencia publica livre; nao e perfeito (EWZ != EM inteiro) mas
# captura o regime de vol de EM emergente com qualidade razoavel.

VIX_PROXY_MAP: dict[str, str] = {
    # US equity indices
    "SPY":  "^VIX",
    "^GSPC": "^VIX",
    "QQQ":  "^VXN",
    "^IXIC": "^VXN",
    "IWM":  "^RVX",
    # Commodities
    "USO":  "^OVX",    # WTI
    "CL=F": "^OVX",
    "BZ=F": "^OVX",    # brent (proxy WTI — nao oficial)
    "GLD":  "^GVZ",
    "SLV":  "^GVZ",    # proxy gold
    "GC=F": "^GVZ",
    # Bonds
    "TLT":  "^VXTLT",
    # Emerging markets
    "EEM":  "^VXEEM",
    "EWZ":  "^VXEEM",  # proxy EM — melhor publico livre pra Brasil
}


# ── Paths ────────────────────────────────────────────────────────────────────

_SERVICE_DIR = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT   = os.path.abspath(os.path.join(_SERVICE_DIR, "..", ".."))
IV_HISTORY_CSV = os.path.join(_REPO_ROOT, "data", "iv_history.csv")


# ── Leitura do CBOE proxy ────────────────────────────────────────────────────

@st.cache_data(ttl=CACHE_TTL, show_spinner=False)
def _cboe_proxy_series(vol_index: str, period: str = "2y") -> pd.Series:
    """Baixa serie de close do indice CBOE. Retorna serie vazia em falha.

    Os indices CBOE sao publicados em pontos (ex.: VIX=16.5 = 16.5% IV).
    Convertemos para decimal (0.165) para casar com a convencao de iv_avg
    do options_service.
    """
    try:
        hist = data.history(vol_index, period=period)
        if hist is None or hist.empty or "Close" not in hist.columns:
            return pd.Series(dtype=float)
        closes = hist["Close"].dropna()
        # Indices CBOE em pontos -> decimal
        return closes / 100.0
    except Exception:
        return pd.Series(dtype=float)


# ── Leitura / escrita do CSV ─────────────────────────────────────────────────

_CSV_COLUMNS = ["date", "ticker", "atm_iv", "atm_hv", "spot"]


def _ensure_csv_exists() -> None:
    """Cria o CSV com cabecalho se nao existir."""
    os.makedirs(os.path.dirname(IV_HISTORY_CSV), exist_ok=True)
    if not os.path.exists(IV_HISTORY_CSV):
        pd.DataFrame(columns=_CSV_COLUMNS).to_csv(IV_HISTORY_CSV, index=False)


@st.cache_data(ttl=CACHE_TTL, show_spinner=False)
def _load_csv() -> pd.DataFrame:
    """Le o CSV inteiro (pequeno — <1MB/ano). Cache 15min."""
    _ensure_csv_exists()
    try:
        df = pd.read_csv(IV_HISTORY_CSV, parse_dates=["date"])
        return df
    except Exception:
        return pd.DataFrame(columns=_CSV_COLUMNS)


def _self_history_series(ticker: str, lookback_days: int = 365) -> pd.Series:
    """Serie de ATM IV (decimal) para `ticker`, dos ultimos N dias corridos."""
    df = _load_csv()
    if df.empty:
        return pd.Series(dtype=float)
    cutoff = datetime.utcnow() - timedelta(days=lookback_days)
    sub = df[(df["ticker"] == ticker) & (df["date"] >= cutoff)].copy()
    if sub.empty:
        return pd.Series(dtype=float)
    sub = sub.sort_values("date").drop_duplicates("date", keep="last")
    return pd.Series(sub["atm_iv"].to_numpy(dtype=float),
                     index=pd.to_datetime(sub["date"]))


def append_snapshot(ticker: str, atm_iv: float, atm_hv: float | None,
                    spot: float | None, date: datetime | None = None) -> None:
    """Adiciona linha ao CSV com o snapshot do dia. Usado pelo script diario.

    Se ja existir linha com (date, ticker), substitui.
    """
    _ensure_csv_exists()
    date = date or datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    day = date.strftime("%Y-%m-%d")
    # Le sem o cache de Streamlit (script roda fora do runtime)
    try:
        df = pd.read_csv(IV_HISTORY_CSV, parse_dates=["date"])
    except Exception:
        df = pd.DataFrame(columns=_CSV_COLUMNS)

    if not df.empty:
        # Normaliza date -> string YYYY-MM-DD para comparacao uniforme
        df["date"] = pd.to_datetime(df["date"], errors="coerce").dt.strftime("%Y-%m-%d")
        mask = (df["date"] == day) & (df["ticker"] == ticker)
        df = df[~mask]

    new = pd.DataFrame([{
        "date":    day,
        "ticker":  ticker,
        "atm_iv":  round(float(atm_iv), 6) if atm_iv is not None else None,
        "atm_hv":  round(float(atm_hv), 6) if atm_hv  is not None else None,
        "spot":    round(float(spot), 6)   if spot    is not None else None,
    }])
    if df.empty:
        df = new
    else:
        df = pd.concat([df, new], ignore_index=True)
    df = df.sort_values(["ticker", "date"])
    df.to_csv(IV_HISTORY_CSV, index=False)


# ── API publica ──────────────────────────────────────────────────────────────

def get_iv_rank(ticker: str, current_iv: float | None) -> dict[str, Any]:
    """IV Rank real com fallback em cascata.

    Prioridade:
      1. CBOE vol index, se mapeado -> IV Rank real imediato
      2. Self-history (data/iv_history.csv) -> IV Rank real apos ramp-up
      3. None com source='insufficient' quando nenhuma fonte tem >=20 pontos

    Args:
        ticker: simbolo do ativo subjacente (ex.: 'PBR', 'SPY').
        current_iv: IV ATM atual (decimal). Se None, retorna source='no_chain'.

    Returns:
        dict:
            rank (float | None): 0-100 ou None
            source (str): 'cboe' | 'self_history' | 'insufficient' | 'no_chain'
            n_days (int): pontos de historico usados (0 se indisponivel)
            current_iv (float | None): IV passado, ecoado pra UI
            vol_index (str | None): qual indice CBOE foi usado (se aplicavel)
    """
    if current_iv is None or (isinstance(current_iv, (int, float)) and current_iv <= 0):
        return {"rank": None, "source": "no_chain", "n_days": 0,
                "current_iv": None, "vol_index": None}

    # 1) CBOE proxy
    vol_index = VIX_PROXY_MAP.get(ticker)
    if vol_index:
        s = _cboe_proxy_series(vol_index)
        rank = oa.calc_iv_rank(current_iv, s)
        if rank is not None:
            return {"rank": rank, "source": "cboe", "n_days": len(s),
                    "current_iv": float(current_iv), "vol_index": vol_index}

    # 2) Self-history
    s = _self_history_series(ticker)
    rank = oa.calc_iv_rank(current_iv, s)
    if rank is not None:
        return {"rank": rank, "source": "self_history", "n_days": len(s),
                "current_iv": float(current_iv), "vol_index": None}

    # 3) Insufficient
    return {"rank": None, "source": "insufficient", "n_days": len(s),
            "current_iv": float(current_iv), "vol_index": None}


def compute_atm_iv(chain: dict, spot: float) -> float | None:
    """ATM IV para snapshot diario.

    Definicao: media ponderada por OI das IVs dos 3 strikes mais proximos
    do spot, expiry 20-45 DTE (ou a mais proxima disponivel).

    Retorna None se chain sem dados utilizaveis.
    """
    if not chain or not chain.get("available"):
        return None

    calls = chain.get("calls", pd.DataFrame())
    puts  = chain.get("puts",  pd.DataFrame())
    if (calls is None or calls.empty) and (puts is None or puts.empty):
        return None

    # Unifica em DataFrame unico com ambos os lados
    frames = []
    if calls is not None and not calls.empty: frames.append(calls)
    if puts  is not None and not puts.empty:  frames.append(puts)
    df = pd.concat(frames, ignore_index=True)

    df = df[(df["impliedVolatility"] > 0) & (df["strike"] > 0)]
    if df.empty:
        return None

    # Prioriza 20-45 DTE; se nao houver, usa expiry mais proxima do alvo (30d)
    target = df[(df["daysToExpiry"] >= 20) & (df["daysToExpiry"] <= 45)]
    if target.empty:
        # Escolhe a expiry com DTE mais proximo de 30
        df["_dist"] = (df["daysToExpiry"] - 30).abs()
        min_dist = df["_dist"].min()
        target = df[df["_dist"] == min_dist].drop(columns=["_dist"])

    # Strikes dentro de ±5% do spot (janela ATM estreita).
    # Fallback: 3 strikes mais proximos se janela ±5% vier vazia.
    target = target.copy()
    lo, hi = float(spot) * 0.95, float(spot) * 1.05
    band = target[(target["strike"] >= lo) & (target["strike"] <= hi)]
    if band.empty:
        target["_k"] = (target["strike"] - float(spot)).abs()
        target = target.nsmallest(3, "_k").drop(columns=["_k"])
    else:
        target = band
    if target.empty:
        return None

    oi = target["openInterest"].to_numpy(dtype=float)
    iv = target["impliedVolatility"].to_numpy(dtype=float)
    mask = (oi > 0) & (iv > 0)
    if not mask.any():
        # fallback: simple mean dos strikes ATM
        iv_only = iv[iv > 0]
        return float(iv_only.mean()) if iv_only.size else None
    return float((iv[mask] * oi[mask]).sum() / oi[mask].sum())
