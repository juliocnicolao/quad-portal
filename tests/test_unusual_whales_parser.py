"""Tests puros (sem rede) para collectors.unusual_whales."""
from __future__ import annotations

import json

import pytest

from collectors.unusual_whales import (
    parse_gex,
    parse_market_state,
    _safe_div,
    _to_float,
    _to_int,
)


# ─── helpers ─────────────────────────────────────────────────────────────────

def test_to_float_accepts_strings_and_floats_and_ints():
    assert _to_float("1.23") == 1.23
    assert _to_float(1.23) == 1.23
    assert _to_float(2) == 2.0
    assert _to_float(None) is None
    assert _to_float("not-a-number") is None
    assert _to_float("") is None


def test_to_int_handles_decimal_strings():
    assert _to_int("1615889") == 1615889
    assert _to_int("1615889.0") == 1615889
    assert _to_int(None) is None
    assert _to_int("nope") is None


def test_safe_div_handles_zero_and_none():
    assert _safe_div(10.0, 2.0) == 5.0
    assert _safe_div(None, 2.0) is None
    assert _safe_div(10.0, 0.0) is None
    assert _safe_div(10.0, None) is None


# ─── parse_market_state ──────────────────────────────────────────────────────

_SAMPLE_FLOW = [{
    "date": "2026-04-20",
    "open": "20.66", "high": "20.82", "low": "20.55", "close": "20.76",
    "call_volume": 27296, "put_volume": 28651,
    "call_premium": "2167022.00", "put_premium": "2852091.00",
    "net_premium": "626384.00",
    "call_open_interest": 829174, "put_open_interest": 786715,
    "total_open_interest": 1615889,
    "iv_rank": "95.07",
    "volatility_30": None, "volatility_60": None,
    "implied_move_perc_30": None, "implied_move_perc_60": None,
    "avg_30_day_call_volume": "56065.9667",
    "avg_30_day_put_volume":  "24821.1333",
    "avg_30_day_call_oi":     "998295.8",
    "avg_30_day_put_oi":      "740412.1667",
    "bullish_premium": "1586165.00", "bearish_premium": "959781.00",
    "ticker": "PBR",
}]


def test_parse_market_state_happy():
    rows = parse_market_state("PBR", _SAMPLE_FLOW)
    assert len(rows) == 1
    r = rows[0]
    assert r["ticker"] == "PBR"
    assert r["date"] == "2026-04-20"
    assert r["open"] == pytest.approx(20.66)
    assert r["close"] == pytest.approx(20.76)
    assert r["c_vol"] == 27296
    assert r["p_vol"] == 28651
    assert r["volume"] == 27296 + 28651
    assert r["pc_ratio"] == pytest.approx(28651 / 27296)
    assert r["total_oi"] == 1615889
    assert r["ivr"] == pytest.approx(95.07)
    assert r["net_prem"] == pytest.approx(626384.0)
    assert r["total_prem"] == pytest.approx(2167022.0 + 2852091.0)
    # pct_change = (close-open)/open
    assert r["pct_change"] == pytest.approx((20.76 - 20.66) / 20.66)
    # vol_30d_ratio = volume / (avg_call + avg_put)
    expected_ratio = (27296 + 28651) / (56065.9667 + 24821.1333)
    assert r["vol_30d_ratio"] == pytest.approx(expected_ratio, rel=1e-4)
    # oi_pct = total_oi / (avg_c_oi + avg_p_oi)
    assert r["oi_pct"] == pytest.approx(1615889 / (998295.8 + 740412.1667), rel=1e-4)
    # source_raw preserva o JSON bruto
    raw = json.loads(r["source_raw"])
    assert raw["ticker"] == "PBR"


def test_parse_market_state_missing_date_skipped():
    rows = parse_market_state("PBR", [{"close": "10.0"}])  # sem date
    assert rows == []


def test_parse_market_state_not_list_raises():
    with pytest.raises(ValueError, match="lista"):
        parse_market_state("PBR", {"not": "a list"})


def test_parse_market_state_handles_null_fields():
    # payload real tem varios null em volatility_*
    minimal = [{"date": "2026-04-20", "close": "10.0", "open": None,
                "call_volume": None, "put_volume": None,
                "iv_rank": None}]
    rows = parse_market_state("PBR", minimal)
    assert len(rows) == 1
    r = rows[0]
    assert r["close"] == 10.0
    assert r["open"] is None
    assert r["c_vol"] is None
    assert r["p_vol"] is None
    # volume=None quando ambos call/put vol sao None
    assert r["volume"] is None
    assert r["pc_ratio"] is None
    assert r["ivr"] is None


def test_parse_market_state_non_dict_items_skipped():
    rows = parse_market_state("PBR", [None, "string", _SAMPLE_FLOW[0]])
    assert len(rows) == 1
    assert rows[0]["date"] == "2026-04-20"


# ─── parse_gex ───────────────────────────────────────────────────────────────

_SAMPLE_GEX = {"data": [
    {"date": "2025-04-21", "close": "11.51",
     "call_gex": "5140228.3726", "put_gex": "-6346876.3570",
     "call_delta": "8562518.2150", "put_delta": "-28065125.5490",
     "call_charm": "-3768007.2112", "put_charm": "-3107203.8226",
     "call_vanna": "17473255.6828", "put_vanna": "13187555.4668"},
    {"date": "2025-04-22", "close": "11.49",
     "call_gex": "4749796.1229", "put_gex": "-7858620.7769",
     "call_delta": "8237091.1562", "put_delta": "-29428975.2891",
     "call_charm": "-4444833.0262", "put_charm": "-2917838.3269",
     "call_vanna": "17864701.3629", "put_vanna": "13438064.1484"},
]}


def test_parse_gex_happy():
    rows = parse_gex("PBR", _SAMPLE_GEX)
    assert len(rows) == 2
    r0 = rows[0]
    assert r0["ticker"] == "PBR"
    assert r0["date"] == "2025-04-21"
    assert r0["close"] == pytest.approx(11.51)
    assert r0["call_gex"] == pytest.approx(5140228.3726)
    assert r0["put_gex"] == pytest.approx(-6346876.3570)
    assert r0["call_delta"] == pytest.approx(8562518.2150)


def test_parse_gex_missing_data_raises():
    with pytest.raises(ValueError, match="data"):
        parse_gex("PBR", {"not_data": []})


def test_parse_gex_not_dict_raises():
    with pytest.raises(ValueError, match="dict"):
        parse_gex("PBR", [1, 2, 3])


def test_parse_gex_skips_items_without_date():
    payload = {"data": [{"close": "10.0"}, _SAMPLE_GEX["data"][0]]}
    rows = parse_gex("PBR", payload)
    assert len(rows) == 1
    assert rows[0]["date"] == "2025-04-21"
