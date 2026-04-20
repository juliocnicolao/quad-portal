"""Options analytics — Black-Scholes, GEX, IV rank, regression channel, scorecard, P&L.

Modulo matematico puro. Zero Streamlit, zero I/O. Totalmente testavel.

Todas as funcoes recebem primitivos ou DataFrames e retornam dict/ndarray/float.
"""

from __future__ import annotations

import datetime as _dt
import math
from typing import Literal

import numpy as np
import pandas as pd
from scipy.stats import norm


# ── Constantes de regime de IV (parametrizadas) ─────────────────────────────
IV_CRASH_THRESHOLD = -0.20   # queda > 20% do spot
IV_CRASH_LEVEL     = 0.65
IV_FALL_THRESHOLD  = -0.10   # queda > 10%
IV_FALL_LEVEL      = 0.55
IV_RALLY_THRESHOLD =  0.10   # alta > 10%
IV_RALLY_LEVEL     = 0.35
IV_BASE_FALLBACK   = 0.50    # usado apenas se iv_avg indisponivel

# Convencao de anualizacao
TRADING_DAYS = 252


# ── Black-Scholes ────────────────────────────────────────────────────────────

def _d1(spot: float, strike: float, t: float, r: float, iv: float) -> float:
    """d1 do Black-Scholes."""
    return (math.log(spot / strike) + (r + 0.5 * iv * iv) * t) / (iv * math.sqrt(t))


def bs_put_price(spot: float, strike: float, days: int, iv: float,
                 r: float = 0.045) -> float:
    """Preco teorico de put europeia (Black-Scholes).

    Args:
        spot: preco atual do underlying.
        strike: strike da put.
        days: dias corridos ate o vencimento. Se <= 0, retorna valor intrinsico.
        iv: volatilidade implicita anualizada (ex.: 0.40 = 40%).
        r: taxa livre de risco anualizada.

    Returns:
        Preco teorico da put (sempre >= 0).
    """
    if days <= 0:
        return max(strike - spot, 0.0)
    if iv <= 0 or spot <= 0 or strike <= 0:
        # Fallback seguro: intrinsico descontado
        return max(strike - spot, 0.0)
    t = days / 365.0
    d1 = _d1(spot, strike, t, r, iv)
    d2 = d1 - iv * math.sqrt(t)
    price = strike * math.exp(-r * t) * norm.cdf(-d2) - spot * norm.cdf(-d1)
    return float(max(price, 0.0))


def bs_call_price(spot: float, strike: float, days: int, iv: float,
                  r: float = 0.045) -> float:
    """Preco teorico de call europeia (Black-Scholes). Usado internamente em GEX."""
    if days <= 0:
        return max(spot - strike, 0.0)
    if iv <= 0 or spot <= 0 or strike <= 0:
        return max(spot - strike, 0.0)
    t = days / 365.0
    d1 = _d1(spot, strike, t, r, iv)
    d2 = d1 - iv * math.sqrt(t)
    price = spot * norm.cdf(d1) - strike * math.exp(-r * t) * norm.cdf(d2)
    return float(max(price, 0.0))


def bs_gamma(spot: float, strike: float, days: int, iv: float,
             r: float = 0.045) -> float:
    """Gamma (Black-Scholes): derivada segunda do preco vs spot.

    gamma = N'(d1) / (spot * iv * sqrt(t))
    """
    if days <= 0 or iv <= 0 or spot <= 0 or strike <= 0:
        return 0.0
    t = days / 365.0
    d1 = _d1(spot, strike, t, r, iv)
    return float(norm.pdf(d1) / (spot * iv * math.sqrt(t)))


# ── GEX (Gamma Exposure) ─────────────────────────────────────────────────────

def calc_gex(chain: dict, spot: float, r: float = 0.045) -> pd.DataFrame:
    """Gamma Exposure agregado por strike.

    CONVENCAO (hipotese padrao de posicionamento dealer):
    - Calls: dealer vendeu ao retail -> contribuicao POSITIVA em GEX
    - Puts:  dealer comprou do retail -> contribuicao NEGATIVA em GEX

    ATENCAO: Esta e uma aproximacao. Posicionamento real pode divergir
    em eventos extremos, venda institucional de puts, etc.

    Formula por contrato:
        gex   = sign * gamma * OI * 100 * spot**2 * 0.01
        gamma = N'(d1) / (spot * iv * sqrt(t))

    Args:
        chain: dict com chaves 'calls' e 'puts', cada uma DataFrame com
               colunas 'strike', 'openInterest', 'impliedVolatility',
               'daysToExpiry' (int).
        spot: preco atual do underlying.
        r: taxa livre de risco.

    Returns:
        DataFrame com colunas ['strike', 'gex_calls', 'gex_puts', 'gex_total'],
        ordenado por strike.
    """
    rows: list[dict] = []
    for kind, sign in (("calls", +1), ("puts", -1)):
        df = chain.get(kind)
        if df is None or df.empty:
            continue
        for _, row in df.iterrows():
            strike = float(row.get("strike") or 0)
            oi     = float(row.get("openInterest") or 0)
            iv     = float(row.get("impliedVolatility") or 0)
            days   = int(row.get("daysToExpiry") or 0)
            if strike <= 0 or oi <= 0 or iv <= 0 or days <= 0:
                continue
            gamma = bs_gamma(spot, strike, days, iv, r=r)
            gex   = sign * gamma * oi * 100.0 * (spot ** 2) * 0.01
            rows.append({"strike": strike, "kind": kind, "gex": gex})

    if not rows:
        return pd.DataFrame(columns=["strike", "gex_calls", "gex_puts", "gex_total"])

    df = pd.DataFrame(rows)
    pivot = df.pivot_table(index="strike", columns="kind", values="gex",
                           aggfunc="sum", fill_value=0.0).reset_index()
    pivot.columns.name = None
    if "calls" not in pivot.columns: pivot["calls"] = 0.0
    if "puts"  not in pivot.columns: pivot["puts"]  = 0.0
    pivot = pivot.rename(columns={"calls": "gex_calls", "puts": "gex_puts"})
    pivot["gex_total"] = pivot["gex_calls"] + pivot["gex_puts"]
    return pivot.sort_values("strike").reset_index(drop=True)


# ── IV Rank (percentil rolling 252d de HV20) ─────────────────────────────────

def calc_hv(closes: pd.Series, window: int = 20) -> pd.Series:
    """Volatilidade historica anualizada, rolling.

    HV = std(log returns) * sqrt(252)
    """
    closes = closes.dropna()
    if len(closes) < 2:
        return pd.Series(dtype=float)
    log_ret = np.log(closes / closes.shift(1)).dropna()
    return log_ret.rolling(window).std() * math.sqrt(TRADING_DAYS)


def calc_iv_rank(closes: pd.Series, window: int = 20,
                 lookback: int = 252) -> float:
    """IV Rank aproximado: percentil da HV20 atual dentro do lookback de 1 ano.

    Retorna 0-100. Em serie insuficiente (<20 pontos), retorna 50.0 (neutro).
    """
    closes = closes.dropna() if closes is not None else pd.Series(dtype=float)
    if len(closes) < window:
        return 50.0
    hv = calc_hv(closes, window=window).dropna()
    if hv.empty:
        return 50.0
    recent = hv.tail(lookback)
    current = float(hv.iloc[-1])
    rank = float((recent <= current).sum()) / float(len(recent)) * 100.0
    return max(0.0, min(100.0, rank))


# ── Canal de regressao ───────────────────────────────────────────────────────

def regression_channel(df: pd.DataFrame, n_std: float = 2.0,
                       current_spot: float | None = None) -> dict:
    """Canal de regressao linear com bandas +/- n_std residuos.

    Usa TODA a serie passada (sem janela fixa interna).

    Args:
        df: DataFrame com coluna 'Close' e DatetimeIndex.
        n_std: numero de desvios para as bandas.
        current_spot: preco atual para calcular position_pct. Se None,
                      usa o ultimo close do DataFrame.

    Returns:
        dict com upper/mean/lower (np.ndarray), slope, intercept,
        residual_std, position_pct (0-100), is_valid (bool), reason (str|None).
    """
    closes = df["Close"].dropna() if df is not None and "Close" in df.columns \
             else pd.Series(dtype=float)

    if len(closes) < 20:
        n = max(len(closes), 1)
        last_price = float(closes.iloc[-1]) if len(closes) > 0 else 0.0
        neutral = np.full(n, last_price)
        return {
            "upper": neutral,
            "mean": neutral,
            "lower": neutral,
            "slope": 0.0,
            "intercept": last_price,
            "residual_std": 0.0,
            "position_pct": 50.0,
            "is_valid": False,
            "reason": f"Serie insuficiente para regressao ({len(closes)} pontos, minimo 20)",
        }

    x = np.arange(len(closes), dtype=float)
    y = closes.to_numpy(dtype=float)
    slope, intercept = np.polyfit(x, y, 1)
    mean  = slope * x + intercept
    residual_std = float(np.std(y - mean, ddof=1))
    upper = mean + n_std * residual_std
    lower = mean - n_std * residual_std

    reference_price = float(current_spot) if current_spot is not None else float(y[-1])
    band = upper[-1] - lower[-1]
    pos = float((reference_price - lower[-1]) / band * 100) if band > 0 else 50.0
    pos = max(0.0, min(100.0, pos))

    return {
        "upper": upper,
        "mean": mean,
        "lower": lower,
        "slope": float(slope),
        "intercept": float(intercept),
        "residual_std": residual_std,
        "position_pct": pos,
        "is_valid": True,
        "reason": None,
    }


# ── Scorecard de convergencia ───────────────────────────────────────────────

Bias = Literal["BEARISH", "NEUTRAL", "BULLISH"]
IVLabel = Literal["HIGH", "MID", "LOW", "N/A"]


def classify_technical(position_pct: float) -> Bias:
    """Posicao no canal -> bias tecnico."""
    if position_pct > 75: return "BEARISH"
    if position_pct < 25: return "BULLISH"
    return "NEUTRAL"


def classify_momentum(change_20d_pct: float) -> Bias:
    """Variacao 20d -> bias de momentum."""
    if change_20d_pct < -5:  return "BEARISH"
    if change_20d_pct > 10:  return "BULLISH"
    return "NEUTRAL"


def classify_options_flow(pc_oi_ratio: float) -> Bias:
    """P/C Open Interest ratio -> bias de fluxo."""
    if pc_oi_ratio > 1.1: return "BEARISH"
    if pc_oi_ratio < 0.7: return "BULLISH"
    return "NEUTRAL"


def classify_iv_rank(iv_rank: float) -> IVLabel:
    """IV Rank -> regime de volatilidade."""
    if iv_rank > 70: return "HIGH"
    if iv_rank < 30: return "LOW"
    return "MID"


def scorecard(technical: Bias | None = None,
              momentum: Bias | None = None,
              options_flow: Bias | None = None,
              iv_rank_label: IVLabel | None = None) -> dict:
    """Agrega pilares em veredito.

    Pilares com valor None sao ignorados (util quando nao ha options chain).
    IV Rank entra como contexto (nao conta na convergencia bear/bull).

    Retorno:
        dict com keys:
        - pillars: lista [{name, bias}] dos pilares avaliados
        - bearish_pct / bullish_pct: % dos pilares bear/bull-countables
        - verdict: 'STRONG_BEARISH' | 'STRONG_BULLISH' | 'MIXED'
        - iv_context: rotulo HIGH/MID/LOW/N/A
    """
    pillars: list[dict] = []
    if technical    is not None: pillars.append({"name": "Tecnico",      "bias": technical})
    if momentum     is not None: pillars.append({"name": "Momentum",     "bias": momentum})
    if options_flow is not None: pillars.append({"name": "Options Flow", "bias": options_flow})

    countable = [p for p in pillars if p["bias"] in ("BEARISH", "BULLISH", "NEUTRAL")]
    total = len(countable)
    if total == 0:
        verdict = "MIXED"
        bear_pct = bull_pct = 0.0
    else:
        bears = sum(1 for p in countable if p["bias"] == "BEARISH")
        bulls = sum(1 for p in countable if p["bias"] == "BULLISH")
        bear_pct = bears / total * 100.0
        bull_pct = bulls / total * 100.0
        if   bear_pct >= 75: verdict = "STRONG_BEARISH"
        elif bull_pct >= 75: verdict = "STRONG_BULLISH"
        else:                verdict = "MIXED"

    return {
        "pillars": pillars,
        "bearish_pct": bear_pct,
        "bullish_pct": bull_pct,
        "verdict": verdict,
        "iv_context": iv_rank_label or "N/A",
    }


# ── Simulador de P&L ─────────────────────────────────────────────────────────

def _iv_for_scenario(spot_ret: float, iv_base: float) -> float:
    """IV a usar num cenario segundo regime por variacao do spot."""
    if spot_ret <= IV_CRASH_THRESHOLD: return IV_CRASH_LEVEL
    if spot_ret <= IV_FALL_THRESHOLD:  return IV_FALL_LEVEL
    if spot_ret >= IV_RALLY_THRESHOLD: return IV_RALLY_LEVEL
    return iv_base


DEFAULT_CUSTOM_LABELS = ["Queda 20%", "Bear base", "Cauda"]


# Presets de teses reais (puts compradas pelo usuario). Mapeia ticker -> lista
# de dicts com strike, expiry (YYYY-MM-DD), contracts, premium_paid. Dias ate
# vencimento sao calculados em tempo de chamada por default_positions().
THESIS_PRESETS: dict[str, list[dict]] = {
    "PBR": [
        {"strike": 15.00, "expiry": "2027-01-15", "contracts": 10, "premium_paid": 0.75},
        {"strike": 17.00, "expiry": "2027-01-15", "contracts": 10, "premium_paid": 1.40},
        {"strike": 18.00, "expiry": "2027-02-19", "contracts": 10, "premium_paid": 2.00},
    ],
}


def default_positions(ticker: str, spot: float, iv_base: float | None = None,
                      today: _dt.date | None = None,
                      r: float = 0.045) -> list[dict]:
    """Retorna lista de posicoes default para exibir no simulador de P&L.

    Se `ticker` tiver preset em THESIS_PRESETS, usa esses valores e calcula
    `days` a partir de `today` (default: hoje). Caso contrario, devolve 1
    posicao generica (ATM, 90 dias, premio aproximado via Black-Scholes
    usando `iv_base` ou IV_BASE_FALLBACK).

    Args:
        ticker: simbolo (case-insensitive).
        spot: preco atual.
        iv_base: IV media da chain (usada no premio BS do fallback).
        today: data de referencia para calcular dias ate vencimento.
        r: taxa livre de risco (usada no premio BS do fallback).

    Returns:
        Lista de dicts com chaves strike, days, contracts, premium_paid.
    """
    today = today or _dt.date.today()
    key = (ticker or "").strip().upper()

    if key in THESIS_PRESETS:
        out = []
        for p in THESIS_PRESETS[key]:
            try:
                exp = _dt.datetime.strptime(p["expiry"], "%Y-%m-%d").date()
                days = max((exp - today).days, 1)
            except Exception:
                days = 90
            out.append({
                "strike":       float(p["strike"]),
                "days":         int(days),
                "contracts":    int(p["contracts"]),
                "premium_paid": float(p["premium_paid"]),
            })
        return out

    # Fallback generico: 1 posicao ATM 90d com premio BS
    iv = iv_base if (iv_base and iv_base > 0) else IV_BASE_FALLBACK
    days = 90
    premium = bs_put_price(spot=spot, strike=spot, days=days, iv=iv, r=r)
    return [{
        "strike":       float(spot),
        "days":         days,
        "contracts":    1,
        "premium_paid": round(float(premium), 2),
    }]


def pnl_scenarios(positions: list[dict], spot: float,
                  custom_spots: list[float] | None = None,
                  custom_labels: list[str] | None = None,
                  iv_base: float | None = None,
                  r: float = 0.045) -> pd.DataFrame:
    """Simula P&L de posicoes de put em varios cenarios de spot.

    Args:
        positions: lista de dicts com chaves:
            strike (float), days (int), contracts (int), premium_paid (float)
        spot: preco atual de referencia.
        custom_spots: ate 3 niveis adicionais de spot. Default: [spot*0.8, spot*0.7, spot*0.55]
            (bear progressivo: Queda 20% -> Bear base -> Cauda).
        custom_labels: rotulos para os 3 cenarios customizaveis.
            Default: ["Queda 20%", "Bear base", "Cauda"].
        iv_base: IV de base (de preferencia iv_avg do chain). Se None, usa IV_BASE_FALLBACK.
        r: taxa livre de risco.

    Returns:
        DataFrame com 1 linha por cenario e colunas:
            scenario, spot, iv_used, pnl_total, pnl_by_position (lista str para display)
    """
    if iv_base is None:
        iv_base = IV_BASE_FALLBACK

    fixed = [
        ("Alta 20%",  spot * 1.20),
        ("Alta 5%",   spot * 1.05),
        ("Atual",     spot * 1.00),
        ("Queda 10%", spot * 0.90),
    ]
    if custom_spots is None:
        custom_spots = [spot * 0.80, spot * 0.70, spot * 0.55]
    if custom_labels is None:
        custom_labels = DEFAULT_CUSTOM_LABELS
    for i, s in enumerate(custom_spots[:3]):
        label = custom_labels[i] if i < len(custom_labels) else f"Custom {i+1}"
        fixed.append((label, float(s)))

    rows = []
    for label, s in fixed:
        spot_ret = (s - spot) / spot if spot else 0.0
        iv_used  = _iv_for_scenario(spot_ret, iv_base)

        total_pnl = 0.0
        leg_details: list[str] = []
        for i, pos in enumerate(positions, start=1):
            strike   = float(pos["strike"])
            days     = int(pos["days"])
            ctrs     = int(pos["contracts"])
            premium  = float(pos["premium_paid"])
            price    = bs_put_price(s, strike, days, iv_used, r=r)
            leg_pnl  = (price - premium) * 100.0 * ctrs
            total_pnl += leg_pnl
            leg_details.append(f"#{i} K${strike:g}: ${leg_pnl:,.0f}")

        rows.append({
            "scenario":         label,
            "spot":             s,
            "iv_used":          iv_used,
            "pnl_total":        total_pnl,
            "pnl_by_position":  " · ".join(leg_details),
        })

    return pd.DataFrame(rows)
