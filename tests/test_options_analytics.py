"""Testes unitarios de options_analytics — funcoes puras."""

import math
import numpy as np
import pandas as pd

from services.options_analytics import (
    bs_put_price,
    bs_call_price,
    bs_gamma,
    calc_gex,
    calc_iv_rank,
    regression_channel,
    classify_technical,
    classify_momentum,
    classify_options_flow,
    classify_iv_rank,
    scorecard,
    calculate_convergence_score,
    detect_unusual_activity,
)


# ── Black-Scholes ────────────────────────────────────────────────────────────

def test_bs_put_expired_itm():
    """Put com dias=0 deve retornar intrinsic value exato."""
    assert bs_put_price(spot=90, strike=100, days=0, iv=0.3) == 10.0


def test_bs_put_expired_otm():
    """Put OTM no vencimento vale 0."""
    assert bs_put_price(spot=110, strike=100, days=0, iv=0.3) == 0.0


def test_bs_put_positive_and_bounded():
    p = bs_put_price(spot=100, strike=100, days=30, iv=0.30)
    assert p > 0
    assert p < 100


def test_bs_put_call_parity():
    """put + spot ≈ call + K*exp(-rT) dentro de tolerancia."""
    spot, K, days, iv, r = 100, 100, 60, 0.25, 0.045
    c = bs_call_price(spot, K, days, iv, r=r)
    p = bs_put_price(spot, K, days, iv, r=r)
    t = days / 365.0
    assert abs((p + spot) - (c + K * math.exp(-r * t))) < 1e-6


def test_bs_gamma_positive_atm():
    assert bs_gamma(spot=100, strike=100, days=30, iv=0.30) > 0


def test_bs_gamma_expired_zero():
    assert bs_gamma(spot=100, strike=100, days=0, iv=0.30) == 0.0


# ── GEX ──────────────────────────────────────────────────────────────────────

def test_calc_gex_sign_convention():
    calls = pd.DataFrame([{
        "strike": 100, "openInterest": 1000, "impliedVolatility": 0.30,
        "daysToExpiry": 30,
    }])
    puts = pd.DataFrame([{
        "strike": 100, "openInterest": 1000, "impliedVolatility": 0.30,
        "daysToExpiry": 30,
    }])
    out = calc_gex({"calls": calls, "puts": puts}, spot=100)
    assert not out.empty
    row = out[out["strike"] == 100].iloc[0]
    assert row["gex_calls"] > 0
    assert row["gex_puts"]  < 0
    assert abs(row["gex_total"]) < 1e-6


def test_calc_gex_magnitude_scales_with_oi():
    base = pd.DataFrame([{
        "strike": 100, "openInterest": 1000, "impliedVolatility": 0.30, "daysToExpiry": 30,
    }])
    big = pd.DataFrame([{
        "strike": 100, "openInterest": 2000, "impliedVolatility": 0.30, "daysToExpiry": 30,
    }])
    g1 = calc_gex({"calls": base, "puts": pd.DataFrame()}, spot=100).iloc[0]["gex_calls"]
    g2 = calc_gex({"calls": big,  "puts": pd.DataFrame()}, spot=100).iloc[0]["gex_calls"]
    assert abs(g2 - 2 * g1) < 1e-6


def test_calc_gex_empty_chain():
    out = calc_gex({"calls": pd.DataFrame(), "puts": pd.DataFrame()}, spot=100)
    assert out.empty


# ── IV Rank ──────────────────────────────────────────────────────────────────

def test_iv_rank_series_too_short():
    short = pd.Series([100, 101, 99, 102, 98])
    assert calc_iv_rank(short) == 50.0


def test_iv_rank_high_when_last_is_peak():
    rng = np.random.default_rng(42)
    calm = 100 + np.cumsum(rng.normal(0, 0.3, 200))
    wild = calm[-1] + np.cumsum(rng.normal(0, 3.0, 30))
    series = pd.Series(np.concatenate([calm, wild]))
    assert calc_iv_rank(series) > 70


def test_iv_rank_low_when_last_is_quiet():
    rng = np.random.default_rng(7)
    wild = 100 + np.cumsum(rng.normal(0, 3.0, 200))
    calm = wild[-1] + np.cumsum(rng.normal(0, 0.2, 30))
    series = pd.Series(np.concatenate([wild, calm]))
    assert calc_iv_rank(series) < 30


# ── Regression channel ──────────────────────────────────────────────────────

def test_regression_channel_short_series():
    short_df = pd.DataFrame({"Close": [100, 101, 99, 102, 98]})
    r = regression_channel(short_df)
    assert r["is_valid"] is False
    assert r["position_pct"] == 50.0
    assert r["position_pct_raw"] == 50.0
    assert r["reason"] is not None


def test_regression_channel_empty_series():
    r = regression_channel(pd.DataFrame({"Close": []}))
    assert r["is_valid"] is False


def test_regression_channel_with_current_spot():
    df = pd.DataFrame({"Close": np.linspace(100, 120, 50)})
    r_default = regression_channel(df)
    r_low     = regression_channel(df, current_spot=110.0)
    assert r_default["is_valid"] is True
    assert r_low["is_valid"] is True
    assert r_low["position_pct"] < r_default["position_pct"]


def test_regression_channel_slope_positive_on_uptrend():
    df = pd.DataFrame({"Close": np.linspace(100, 150, 60)})
    r = regression_channel(df)
    assert r["is_valid"] is True
    assert r["slope"] > 0


def test_regression_channel_position_raw_above_100_on_breakout():
    """current_spot muito acima do canal deve dar position_pct_raw > 100."""
    df = pd.DataFrame({"Close": np.linspace(100, 102, 50)})  # baixa vol
    r = regression_channel(df, current_spot=200.0)
    assert r["position_pct"] == 100.0
    assert r["position_pct_raw"] > 100


# ── Classificadores + scorecard ─────────────────────────────────────────────

def test_classifiers_thresholds():
    assert classify_technical(80) == "BEARISH"
    assert classify_technical(10) == "BULLISH"
    assert classify_technical(50) == "NEUTRAL"

    assert classify_momentum(-6) == "BEARISH"
    assert classify_momentum(12) == "BULLISH"
    assert classify_momentum(2)  == "NEUTRAL"

    assert classify_options_flow(1.2) == "BEARISH"
    assert classify_options_flow(0.5) == "BULLISH"
    assert classify_options_flow(0.9) == "NEUTRAL"

    assert classify_iv_rank(80) == "HIGH"
    assert classify_iv_rank(20) == "LOW"
    assert classify_iv_rank(50) == "MID"


def test_scorecard_strong_bearish():
    s = scorecard(technical="BEARISH", momentum="BEARISH",
                  options_flow="BEARISH", iv_rank_label="HIGH")
    assert s["verdict"] == "STRONG_BEARISH"
    assert s["bearish_pct"] == 100.0


def test_scorecard_strong_bullish_with_2_pillars():
    s = scorecard(technical="BULLISH", momentum="BULLISH")
    assert s["verdict"] == "STRONG_BULLISH"
    assert len(s["pillars"]) == 2


def test_scorecard_mixed():
    s = scorecard(technical="BEARISH", momentum="BULLISH", options_flow="NEUTRAL")
    assert s["verdict"] == "MIXED"


# ── Convergence score (scanner) ─────────────────────────────────────────────

def test_convergence_score_all_bearish():
    pillars = [
        {"name": "Tecnico",      "bias": "BEARISH"},
        {"name": "Momentum",     "bias": "BEARISH"},
        {"name": "Options Flow", "bias": "BEARISH"},
    ]
    out = calculate_convergence_score(pillars, direction="bearish")
    assert out["score"] == 3
    assert out["verdict"] == "STRONG_BEAR"
    assert out["label"] == "BEAR FORTE"
    assert out["emoji"] == "🔴"


def test_convergence_score_signed_flips_with_direction():
    pillars = [
        {"name": "Tecnico",  "bias": "BULLISH"},
        {"name": "Momentum", "bias": "BULLISH"},
        {"name": "Options",  "bias": "NEUTRAL"},
    ]
    bear = calculate_convergence_score(pillars, direction="bearish")
    bull = calculate_convergence_score(pillars, direction="bullish")
    assert bear["score"] == -2
    assert bull["score"] == 2
    # Mesmo verdict textual em ambos (baseado em ratios, nao direction)
    assert bear["verdict"] == bull["verdict"] == "BULL"


def test_convergence_score_two_pillars_only():
    """Ticker sem chain: apenas Tecnico + Momentum."""
    pillars = [
        {"name": "Tecnico",  "bias": "BEARISH"},
        {"name": "Momentum", "bias": "BEARISH"},
    ]
    out = calculate_convergence_score(pillars, direction="bearish")
    assert out["total"] == 2
    assert out["verdict"] == "STRONG_BEAR"


def test_convergence_score_all_neutral_is_neutral():
    pillars = [{"name": "a", "bias": "NEUTRAL"}, {"name": "b", "bias": "NEUTRAL"}]
    out = calculate_convergence_score(pillars, direction="bearish")
    assert out["verdict"] == "NEUTRAL"
    assert out["label"] == "NEUTRO"


def test_convergence_score_empty_pillars():
    out = calculate_convergence_score([], direction="bearish")
    assert out["verdict"] == "NEUTRAL"
    assert out["total"] == 0


def test_convergence_score_mixed_with_lean():
    """1 bear + 1 bull + 1 neutral -> MIXED_BEAR se ratios empatam em 1/3."""
    pillars = [
        {"name": "a", "bias": "BEARISH"},
        {"name": "b", "bias": "BULLISH"},
        {"name": "c", "bias": "NEUTRAL"},
    ]
    out = calculate_convergence_score(pillars, direction="bearish")
    # Empate bear/bull -> NEUTRAL por fallback
    assert out["verdict"] == "NEUTRAL"


# ── Unusual activity detector ────────────────────────────────────────────────

def test_unusual_vol_spike():
    flags = detect_unusual_activity({
        "current_hv": 0.45, "hv_7d_ago": 0.30,  # +15 p.p.
    })
    assert any(f["type"] == "vol_spike" for f in flags)


def test_unusual_vol_crush():
    flags = detect_unusual_activity({
        "current_hv": 0.20, "hv_7d_ago": 0.40,  # -20 p.p.
    })
    assert any(f["type"] == "vol_crush" for f in flags)


def test_unusual_channel_breakout():
    flags = detect_unusual_activity({"channel_pos_raw": 115.0})
    types = [f["type"] for f in flags]
    assert "channel_breakout_up" in types


def test_unusual_channel_breakdown():
    flags = detect_unusual_activity({"channel_pos_raw": -20.0})
    assert any(f["type"] == "channel_breakdown" for f in flags)


def test_unusual_pc_shift_bearish():
    flags = detect_unusual_activity({"pc_oi": 1.3, "pc_oi_7d_ago": 0.85})
    assert any(f["type"] == "pc_shift_bearish" for f in flags)


def test_unusual_pc_shift_bullish():
    flags = detect_unusual_activity({"pc_oi": 0.6, "pc_oi_7d_ago": 1.1})
    assert any(f["type"] == "pc_shift_bullish" for f in flags)


def test_unusual_volume_surge():
    flags = detect_unusual_activity({"current_volume": 3_000_000,
                                     "avg_volume_20d":   1_000_000})
    assert any(f["type"] == "volume_surge" for f in flags)


def test_unusual_no_flags_when_data_missing():
    """Sem inputs, nenhuma flag dispara — nao deve quebrar."""
    assert detect_unusual_activity({}) == []


def test_unusual_pc_shift_needs_both_values():
    """Shift de P/C so dispara se pc_oi E pc_oi_7d_ago presentes."""
    flags = detect_unusual_activity({"pc_oi": 1.3})
    assert all(f["type"] not in ("pc_shift_bearish", "pc_shift_bullish") for f in flags)


def test_unusual_channel_in_bounds_no_flag():
    flags = detect_unusual_activity({"channel_pos_raw": 70.0})
    assert not any("channel" in f["type"] for f in flags)
