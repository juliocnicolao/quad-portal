"""Testes do iv_history_service — CBOE proxy map + compute_atm_iv + storage."""

from __future__ import annotations

import os
import tempfile
from datetime import datetime

import pandas as pd
import pytest

from services import iv_history_service as ivs


# ── VIX_PROXY_MAP ────────────────────────────────────────────────────────────

def test_vix_proxy_map_covers_major_etfs():
    must_have = ["SPY", "QQQ", "IWM", "USO", "GLD", "TLT", "EEM", "EWZ"]
    for t in must_have:
        assert t in ivs.VIX_PROXY_MAP, f"{t} deveria ter vol index mapeado"


def test_vix_proxy_map_uses_cboe_symbols():
    """Indices oficiais comecam com ^ (convencao Yahoo para indices)."""
    for idx in ivs.VIX_PROXY_MAP.values():
        assert idx.startswith("^"), f"{idx} nao parece simbolo de indice"


# ── compute_atm_iv ───────────────────────────────────────────────────────────

def _make_chain(strikes_ivs_oi: list[tuple[float, float, int]],
                dte: int = 30) -> dict:
    """Monta chain de teste. strikes_ivs_oi: [(strike, iv, oi), ...]."""
    rows = [{"strike": s, "impliedVolatility": iv, "openInterest": oi,
             "daysToExpiry": dte} for s, iv, oi in strikes_ivs_oi]
    df = pd.DataFrame(rows)
    return {"available": True, "calls": df, "puts": pd.DataFrame()}


def test_compute_atm_iv_empty_chain_returns_none():
    assert ivs.compute_atm_iv({"available": False}, spot=100) is None
    assert ivs.compute_atm_iv({"available": True,
                                "calls": pd.DataFrame(),
                                "puts":  pd.DataFrame()}, spot=100) is None


def test_compute_atm_iv_oi_weighted():
    """ATM IV deve ser media ponderada por OI nos strikes mais proximos."""
    # 3 strikes ATM: 99, 100, 101 com OIs e IVs diferentes
    chain = _make_chain([
        (99,  0.30, 100),
        (100, 0.40, 500),
        (101, 0.35, 100),
        (150, 0.80, 1000),  # far OTM — nao deve dominar
        (50,  0.20, 1000),  # far ITM — nao deve dominar
    ])
    iv = ivs.compute_atm_iv(chain, spot=100)
    # Deve estar na faixa dos strikes proximos (0.30-0.40)
    assert iv is not None
    assert 0.30 < iv < 0.45


def test_compute_atm_iv_skips_zero_iv():
    chain = _make_chain([(100, 0.0, 500), (101, 0.35, 100)])
    iv = ivs.compute_atm_iv(chain, spot=100)
    assert iv is not None
    assert iv > 0


def test_compute_atm_iv_prefers_20_45_dte():
    """Se tiver expiry no range 20-45, usa; senao fallback."""
    rows = [
        {"strike": 100, "impliedVolatility": 0.50, "openInterest": 100,
         "daysToExpiry": 5},
        {"strike": 100, "impliedVolatility": 0.30, "openInterest": 500,
         "daysToExpiry": 30},
    ]
    chain = {"available": True, "calls": pd.DataFrame(rows),
             "puts": pd.DataFrame()}
    iv = ivs.compute_atm_iv(chain, spot=100)
    # Deve usar o 30 DTE (0.30), nao o 5 DTE (0.50)
    assert abs(iv - 0.30) < 0.05


# ── append_snapshot / persistencia ───────────────────────────────────────────

def test_append_snapshot_creates_csv(monkeypatch, tmp_path):
    fake_csv = tmp_path / "iv_history.csv"
    monkeypatch.setattr(ivs, "IV_HISTORY_CSV", str(fake_csv))

    ivs.append_snapshot("PBR", atm_iv=0.45, atm_hv=0.40, spot=20.0,
                         date=datetime(2025, 4, 15))
    assert fake_csv.exists()
    df = pd.read_csv(fake_csv)
    assert len(df) == 1
    assert df.iloc[0]["ticker"] == "PBR"
    assert abs(df.iloc[0]["atm_iv"] - 0.45) < 1e-6


def test_append_snapshot_dedupe_same_day(monkeypatch, tmp_path):
    fake_csv = tmp_path / "iv_history.csv"
    monkeypatch.setattr(ivs, "IV_HISTORY_CSV", str(fake_csv))

    ivs.append_snapshot("PBR", 0.45, 0.40, 20.0, date=datetime(2025, 4, 15))
    ivs.append_snapshot("PBR", 0.50, 0.42, 21.0, date=datetime(2025, 4, 15))
    df = pd.read_csv(fake_csv)
    # Apenas 1 linha (a ultima substitui)
    assert len(df) == 1
    assert abs(df.iloc[0]["atm_iv"] - 0.50) < 1e-6


def test_append_snapshot_multiple_tickers_same_day(monkeypatch, tmp_path):
    fake_csv = tmp_path / "iv_history.csv"
    monkeypatch.setattr(ivs, "IV_HISTORY_CSV", str(fake_csv))

    ivs.append_snapshot("PBR",  0.45, 0.40, 20.0, date=datetime(2025, 4, 15))
    ivs.append_snapshot("VALE", 0.35, 0.30, 17.0, date=datetime(2025, 4, 15))
    df = pd.read_csv(fake_csv)
    assert len(df) == 2
    assert set(df["ticker"]) == {"PBR", "VALE"}


# ── get_iv_rank — fallback cascade ───────────────────────────────────────────

def test_get_iv_rank_no_chain_when_current_iv_none():
    out = ivs.get_iv_rank("PBR", current_iv=None)
    assert out["source"] == "no_chain"
    assert out["rank"] is None


def test_get_iv_rank_no_chain_when_current_iv_zero():
    out = ivs.get_iv_rank("PBR", current_iv=0)
    assert out["source"] == "no_chain"


def test_get_iv_rank_insufficient_for_unknown_ticker(monkeypatch, tmp_path):
    """Ticker sem CBOE proxy E sem self-history -> insufficient."""
    fake_csv = tmp_path / "iv_history.csv"
    fake_csv.write_text("date,ticker,atm_iv,atm_hv,spot\n")
    monkeypatch.setattr(ivs, "IV_HISTORY_CSV", str(fake_csv))
    ivs._load_csv.clear()  # limpa cache Streamlit
    # Bloqueia a perna CBOE: forca ticker sem mapeamento
    out = ivs.get_iv_rank("NONEXISTENT_TICKER_XYZ", current_iv=0.40)
    assert out["source"] in ("insufficient", "no_chain")
    assert out["rank"] is None
