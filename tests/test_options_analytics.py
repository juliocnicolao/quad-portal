"""Testes unitarios de options_analytics — funcoes puras."""

import math
import numpy as np
import pandas as pd
import pytest

import datetime as _dt

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
    pnl_scenarios,
    default_positions,
    DEFAULT_CUSTOM_LABELS,
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
    assert p < 100  # nao pode valer mais que o strike


def test_bs_put_call_parity():
    """put + spot ≈ call + K*exp(-rT) dentro de tolerancia."""
    spot, K, days, iv, r = 100, 100, 60, 0.25, 0.045
    c = bs_call_price(spot, K, days, iv, r=r)
    p = bs_put_price(spot, K, days, iv, r=r)
    t = days / 365.0
    assert abs((p + spot) - (c + K * math.exp(-r * t))) < 1e-6


def test_bs_gamma_positive_atm():
    g = bs_gamma(spot=100, strike=100, days=30, iv=0.30)
    assert g > 0


def test_bs_gamma_expired_zero():
    assert bs_gamma(spot=100, strike=100, days=0, iv=0.30) == 0.0


# ── GEX ──────────────────────────────────────────────────────────────────────

def test_calc_gex_sign_convention():
    """Calls devem gerar GEX positivo e puts GEX negativo."""
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
    # Mesmo gamma, mesma OI -> soma ≈ 0
    assert abs(row["gex_total"]) < 1e-6


def test_calc_gex_magnitude_scales_with_oi():
    """Dobrando OI, GEX (modulo) dobra."""
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
    """Serie com menos de 20 pontos deve retornar 50.0 sem quebrar."""
    short = pd.Series([100, 101, 99, 102, 98])
    assert calc_iv_rank(short) == 50.0


def test_iv_rank_high_when_last_is_peak():
    """Se a volatilidade recente estourou, rank deve ser alto."""
    rng = np.random.default_rng(42)
    calm = 100 + np.cumsum(rng.normal(0, 0.3, 200))
    wild = calm[-1] + np.cumsum(rng.normal(0, 3.0, 30))
    series = pd.Series(np.concatenate([calm, wild]))
    rank = calc_iv_rank(series)
    assert rank > 70


def test_iv_rank_low_when_last_is_quiet():
    rng = np.random.default_rng(7)
    wild = 100 + np.cumsum(rng.normal(0, 3.0, 200))
    calm = wild[-1] + np.cumsum(rng.normal(0, 0.2, 30))
    series = pd.Series(np.concatenate([wild, calm]))
    rank = calc_iv_rank(series)
    assert rank < 30


# ── Regression channel ───────────────────────────────────────────────────────

def test_regression_channel_short_series():
    """Serie com < 20 pontos deve retornar is_valid=False sem quebrar."""
    short_df = pd.DataFrame({"Close": [100, 101, 99, 102, 98]})
    result = regression_channel(short_df)
    assert result["is_valid"] is False
    assert result["position_pct"] == 50.0
    assert result["reason"] is not None


def test_regression_channel_empty_series():
    empty_df = pd.DataFrame({"Close": []})
    result = regression_channel(empty_df)
    assert result["is_valid"] is False


def test_regression_channel_with_current_spot():
    """position_pct reflete current_spot, nao ultimo close.

    Serie linear 100->120: ultimo close (120) fica no topo do canal (pos ≈ 50 na mean,
    mas com residuos pequenos o pos do ultimo ponto e proximo da mean=50). Testamos
    que passando spot mais baixo, a posicao vai mais para baixo que sem passar.
    """
    df = pd.DataFrame({"Close": np.linspace(100, 120, 50)})
    r_default = regression_channel(df)
    r_low     = regression_channel(df, current_spot=110.0)
    assert r_default["is_valid"] is True
    assert r_low["is_valid"] is True
    # Com spot abaixo do ultimo close (120 vs 110), position_pct deve cair
    assert r_low["position_pct"] < r_default["position_pct"]


def test_regression_channel_slope_positive_on_uptrend():
    df = pd.DataFrame({"Close": np.linspace(100, 150, 60)})
    r = regression_channel(df)
    assert r["is_valid"] is True
    assert r["slope"] > 0


# ── Classificadores + scorecard ──────────────────────────────────────────────

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
    """Sem options chain: apenas tecnico + momentum -> ≥75% bull = STRONG_BULLISH."""
    s = scorecard(technical="BULLISH", momentum="BULLISH")
    assert s["verdict"] == "STRONG_BULLISH"
    assert len(s["pillars"]) == 2


def test_scorecard_mixed():
    s = scorecard(technical="BEARISH", momentum="BULLISH", options_flow="NEUTRAL")
    assert s["verdict"] == "MIXED"


# ── P&L simulator ────────────────────────────────────────────────────────────

def test_pnl_scenarios_shape_and_labels():
    positions = [
        {"strike": 50, "days": 60, "contracts": 10, "premium_paid": 1.5},
        {"strike": 55, "days": 90, "contracts": 5,  "premium_paid": 3.0},
    ]
    df = pnl_scenarios(positions, spot=50.0, iv_base=0.40)
    # 4 fixos + 3 custom default (rotulos bear progressivo)
    assert len(df) == 7
    assert set(["scenario", "spot", "iv_used", "pnl_total"]).issubset(df.columns)
    # Rotulos novos devem aparecer
    scenarios = set(df["scenario"])
    assert "Atual" in scenarios
    for lbl in DEFAULT_CUSTOM_LABELS:
        assert lbl in scenarios


def test_pnl_scenarios_put_gains_on_crash():
    """Puts OTM/ATM compradas ganham em crash (cenario Cauda)."""
    positions = [{"strike": 50, "days": 60, "contracts": 10, "premium_paid": 1.5}]
    df = pnl_scenarios(positions, spot=50.0, iv_base=0.40)
    atual = df[df["scenario"] == "Atual"].iloc[0]["pnl_total"]
    crash = df[df["scenario"] == "Cauda"].iloc[0]["pnl_total"]  # spot*0.55
    assert crash > atual


def test_pnl_scenarios_single_position_mode():
    """Modo sem puts reais (show_real_positions=False equivalente): 1 posicao."""
    positions = [{"strike": 30, "days": 90, "contracts": 1, "premium_paid": 1.5}]
    df = pnl_scenarios(positions, spot=30.0, iv_base=0.45)
    assert len(df) == 7
    # P&L por posicao deve ter somente 1 leg
    assert all("#1" in s and "#2" not in s for s in df["pnl_by_position"])


def test_pnl_uses_iv_base_when_no_regime():
    """No cenario 'Atual' (sem mudanca de regime) deve usar iv_base."""
    positions = [{"strike": 50, "days": 60, "contracts": 1, "premium_paid": 1.0}]
    df = pnl_scenarios(positions, spot=50.0, iv_base=0.33)
    row = df[df["scenario"] == "Atual"].iloc[0]
    assert abs(row["iv_used"] - 0.33) < 1e-9


# ── default_positions / presets condicionais ────────────────────────────────

def test_default_positions_pbr_preset():
    """Ticker PBR deve materializar as 3 puts da tese com dias calculados."""
    today = _dt.date(2026, 4, 19)
    pos = default_positions("PBR", spot=14.0, iv_base=0.60, today=today)
    assert len(pos) == 3
    strikes = sorted(p["strike"] for p in pos)
    assert strikes == [15.0, 17.0, 18.0]
    # premios exatos da tese
    premiums = sorted(p["premium_paid"] for p in pos)
    assert premiums == [0.75, 1.40, 2.00]
    # todos com 10 contratos
    assert all(p["contracts"] == 10 for p in pos)
    # dias ate vencimento: 2027-01-15 = 271, 2027-02-19 = 306
    days = sorted(p["days"] for p in pos)
    assert days == [271, 271, 306]


def test_default_positions_generic_fallback():
    """Ticker sem preset: 1 posicao ATM 90d com premio BS > 0."""
    pos = default_positions("SPY", spot=500.0, iv_base=0.20)
    assert len(pos) == 1
    assert pos[0]["strike"] == 500.0
    assert pos[0]["days"] == 90
    assert pos[0]["contracts"] == 1
    assert pos[0]["premium_paid"] > 0


def test_default_positions_case_insensitive():
    """pbr/PBR/Pbr devem todos bater no preset."""
    today = _dt.date(2026, 4, 19)
    for t in ("pbr", "PBR", "Pbr"):
        assert len(default_positions(t, spot=14.0, today=today)) == 3


def test_default_positions_non_preset_ticker_is_not_pbr():
    """Ticker arbitrario nao deve herdar preset de PBR."""
    pos = default_positions("AAPL", spot=200.0, iv_base=0.25)
    assert len(pos) == 1  # apenas a posicao generica
    # Nao deve conter strikes do preset PBR
    assert pos[0]["strike"] == 200.0
