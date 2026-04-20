"""Options analytics — Black-Scholes, GEX, IV rank, regression channel, scorecard, P&L.

Modulo matematico puro. Zero Streamlit, zero I/O. Totalmente testavel.

Todas as funcoes recebem primitivos ou DataFrames e retornam dict/ndarray/float.
"""

from __future__ import annotations

import math
from typing import Literal

import numpy as np
import pandas as pd
from scipy.stats import norm


# IV base fallback: usado como proxy quando chain indisponivel/vazio.
IV_BASE_FALLBACK = 0.50

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


# ── Volatilidade historica (HV) ──────────────────────────────────────────────

def calc_hv(closes: pd.Series, window: int = 20) -> pd.Series:
    """Volatilidade historica anualizada, rolling.

    HV = std(log returns) * sqrt(252)
    """
    closes = closes.dropna()
    if len(closes) < 2:
        return pd.Series(dtype=float)
    log_ret = np.log(closes / closes.shift(1)).dropna()
    return log_ret.rolling(window).std() * math.sqrt(TRADING_DAYS)


# ── IV Rank — percentil puro ─────────────────────────────────────────────────
#
# Convencao: IV Rank = % dos dias historicos em que a IV foi <= IV atual.
# Ex.: rank=80 significa "IV hoje esta no 80o percentil — historicamente cara".
#
# Fonte do historical_series pode ser:
#   (a) serie de vol index da CBOE (^VIX, ^VXN, etc) -> IV Rank real, imediato
#   (b) snapshots proprios de ATM IV acumulados em data/iv_history.csv
#
# Minimo de 20 pontos para retornar numero. Senao, None (dado insuficiente).

MIN_IV_HISTORY_POINTS = 20


def calc_iv_rank(current_iv: float,
                 historical_iv: pd.Series) -> float | None:
    """IV Rank como percentil de current_iv em historical_iv.

    Args:
        current_iv: IV atual (decimal, ex.: 0.35 = 35%).
        historical_iv: serie historica de IV (decimal).

    Returns:
        0-100 se len(historical) >= MIN_IV_HISTORY_POINTS, senao None.
    """
    if current_iv is None or historical_iv is None:
        return None
    try:
        cur = float(current_iv)
    except (TypeError, ValueError):
        return None
    if cur <= 0:
        return None
    # Aceita Series ou qualquer iteravel; se vier DataFrame, pega 1a coluna.
    try:
        if isinstance(historical_iv, pd.DataFrame):
            if historical_iv.shape[1] == 0:
                return None
            s = historical_iv.iloc[:, 0]
        elif isinstance(historical_iv, pd.Series):
            s = historical_iv
        else:
            s = pd.Series(historical_iv)
        s = pd.to_numeric(s, errors="coerce").dropna()
        s = s[s > 0]
    except Exception:
        return None
    n = int(len(s))
    if n < MIN_IV_HISTORY_POINTS:
        return None
    rank = float((s <= cur).sum()) / float(n) * 100.0
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
            "position_pct_raw": 50.0,
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
    pos_raw = float((reference_price - lower[-1]) / band * 100) if band > 0 else 50.0
    pos = max(0.0, min(100.0, pos_raw))

    return {
        "upper": upper,
        "mean": mean,
        "lower": lower,
        "slope": float(slope),
        "intercept": float(intercept),
        "residual_std": residual_std,
        "position_pct": pos,
        "position_pct_raw": pos_raw,  # sem clamp — >100 ou <0 indica rompimento
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


def classify_iv_rank(iv_rank: float | None) -> IVLabel:
    """IV Rank -> regime de volatilidade. None -> N/A."""
    if iv_rank is None: return "N/A"
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


# ── Convergence score (scanner) ──────────────────────────────────────────────

# Veredito: tupla (label curto, emoji, cor semantica da UI)
_VERDICT_MAP = {
    "STRONG_BEAR": ("BEAR FORTE", "🔴", "bearish"),
    "BEAR":        ("BEAR",       "🔴", "bearish"),
    "STRONG_BULL": ("BULL FORTE", "🟢", "bullish"),
    "BULL":        ("BULL",       "🟢", "bullish"),
    "MIXED_BEAR":  ("MISTO bear", "🟡", "mixed"),
    "MIXED_BULL":  ("MISTO bull", "🟡", "mixed"),
    "NEUTRAL":     ("NEUTRO",     "⚪", "neutral"),
}


def calculate_convergence_score(pillars: list[dict],
                                direction: Literal["bearish", "bullish"] = "bearish",
                                ) -> dict:
    """Sumariza scorecard em score assinado + veredito legivel para a tabela.

    Args:
        pillars: lista [{name, bias}] conforme retornada por scorecard()['pillars'].
                 `bias` pode ser 'BEARISH' | 'BULLISH' | 'NEUTRAL' ou None.
        direction: direcao de interesse — score positivo favorece essa direcao.

    Returns:
        dict com:
            - score (int): pilares_favor - pilares_contra (assinado p/ direction)
            - bear_count / bull_count (int)
            - total (int): pilares avaliados (nao-None, nao-NEUTRAL ignorado? nao —
              total conta todos os pilares presentes, inclusive NEUTRAL)
            - verdict (str): codigo em _VERDICT_MAP
            - label (str), emoji (str), color (str)
    """
    valid = [p for p in pillars if p.get("bias") in ("BEARISH", "BULLISH", "NEUTRAL")]
    total = len(valid)
    bears = sum(1 for p in valid if p["bias"] == "BEARISH")
    bulls = sum(1 for p in valid if p["bias"] == "BULLISH")

    if direction == "bearish":
        score = bears - bulls
    else:
        score = bulls - bears

    # Classificacao
    if total == 0:
        verdict = "NEUTRAL"
    else:
        ratio_bear = bears / total
        ratio_bull = bulls / total
        if ratio_bear == 1.0 and total >= 3:   verdict = "STRONG_BEAR"
        elif ratio_bear >= 0.75:               verdict = "STRONG_BEAR"
        elif ratio_bull == 1.0 and total >= 3: verdict = "STRONG_BULL"
        elif ratio_bull >= 0.75:               verdict = "STRONG_BULL"
        elif bears > bulls and bears >= 2:     verdict = "BEAR"
        elif bulls > bears and bulls >= 2:     verdict = "BULL"
        elif bears > bulls:                    verdict = "MIXED_BEAR"
        elif bulls > bears:                    verdict = "MIXED_BULL"
        else:                                  verdict = "NEUTRAL"

    label, emoji, color = _VERDICT_MAP[verdict]
    return {
        "score":      score,
        "bear_count": bears,
        "bull_count": bulls,
        "total":      total,
        "verdict":    verdict,
        "label":      label,
        "emoji":      emoji,
        "color":      color,
    }


# ── Unusual activity detector ────────────────────────────────────────────────

# Thresholds (em pontos percentuais de HV anualizada, exceto onde indicado)
UA_VOL_SPIKE_THRESHOLD   = 10.0   # HV atual - HV 7d > 10 p.p.
UA_VOL_CRUSH_THRESHOLD   = 10.0   # HV 7d - HV atual > 10 p.p.
UA_CHANNEL_BREAK_PAD     = 5.0    # spot > upper + 5% da banda, ou < lower - 5%
UA_PC_SHIFT_BEARISH_CUR  = 1.2
UA_PC_SHIFT_BEARISH_PREV = 0.9
UA_PC_SHIFT_BULLISH_CUR  = 0.7
UA_PC_SHIFT_BULLISH_PREV = 1.0
UA_VOLUME_SURGE_MULT     = 2.0    # volume hoje > 2x media 20d


def detect_unusual_activity(snapshot: dict) -> list[dict]:
    """Detecta sinais anomalos para 1 ticker. Funcao pura.

    `snapshot` aceita (todas as chaves opcionais; flag so dispara se dados disponiveis):
        - current_hv (float, decimal ex. 0.35 = 35%)
        - hv_7d_ago  (float, decimal)
        - channel_pos_raw (float): posicao no canal SEM clamp. >100 = acima da banda,
          <0 = abaixo. Usado para detectar rompimento.
        - pc_oi (float), pc_oi_7d_ago (float | None): P/C OI atual e 7d atras.
          Se 7d_ago indisponivel, flags de shift nao disparam.
        - current_volume (float), avg_volume_20d (float): volume do ativo underlying.

    Returns:
        Lista de {type, label, magnitude, severity} onde severity in
        {'bearish','bullish','neutral'}.
    """
    flags: list[dict] = []

    cur_hv = snapshot.get("current_hv")
    hv7    = snapshot.get("hv_7d_ago")
    if cur_hv is not None and hv7 is not None:
        diff_pp = (float(cur_hv) - float(hv7)) * 100
        if diff_pp > UA_VOL_SPIKE_THRESHOLD:
            flags.append({
                "type": "vol_spike",
                "label": "Volatilidade disparou",
                "magnitude": diff_pp,
                "severity": "neutral",
            })
        elif -diff_pp > UA_VOL_CRUSH_THRESHOLD:
            flags.append({
                "type": "vol_crush",
                "label": "Volatilidade colapsou",
                "magnitude": -diff_pp,
                "severity": "neutral",
            })

    pos_raw = snapshot.get("channel_pos_raw")
    if pos_raw is not None:
        if pos_raw > 100 + UA_CHANNEL_BREAK_PAD:
            flags.append({
                "type": "channel_breakout_up",
                "label": "Rompeu topo do canal",
                "magnitude": float(pos_raw) - 100,
                "severity": "bullish",
            })
        elif pos_raw < 0 - UA_CHANNEL_BREAK_PAD:
            flags.append({
                "type": "channel_breakdown",
                "label": "Rompeu piso do canal",
                "magnitude": abs(float(pos_raw)),
                "severity": "bearish",
            })

    pc = snapshot.get("pc_oi")
    pc_prev = snapshot.get("pc_oi_7d_ago")
    if pc is not None and pc_prev is not None and pc > 0 and pc_prev > 0:
        if pc >= UA_PC_SHIFT_BEARISH_CUR and pc_prev <= UA_PC_SHIFT_BEARISH_PREV:
            flags.append({
                "type": "pc_shift_bearish",
                "label": "P/C virou bearish",
                "magnitude": float(pc) - float(pc_prev),
                "severity": "bearish",
            })
        elif pc <= UA_PC_SHIFT_BULLISH_CUR and pc_prev >= UA_PC_SHIFT_BULLISH_PREV:
            flags.append({
                "type": "pc_shift_bullish",
                "label": "P/C virou bullish",
                "magnitude": float(pc_prev) - float(pc),
                "severity": "bullish",
            })

    vol    = snapshot.get("current_volume")
    vol_avg = snapshot.get("avg_volume_20d")
    if vol is not None and vol_avg is not None and vol_avg > 0:
        ratio = float(vol) / float(vol_avg)
        if ratio >= UA_VOLUME_SURGE_MULT:
            flags.append({
                "type": "volume_surge",
                "label": "Volume anormal",
                "magnitude": ratio,
                "severity": "neutral",
            })

    return flags
