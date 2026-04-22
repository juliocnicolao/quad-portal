"""Collector: options flow + GEX diario via Unusual Whales (sem login).

Fonte: phx.unusualwhales.com (API publica consumida pelo frontend em
unusualwhales.com/stock/{ticker}/overview). Dois endpoints sao usados:

1. /api/market_state_all/{ticker}?limit=1
   Retorna array de dicts por data (ate ~30d). Campos relevantes:
   date, open, high, low, close, call_volume, put_volume,
   call_open_interest, put_open_interest, call_premium, put_premium,
   net_premium, iv_rank, avg_30_day_call_volume, avg_30_day_put_volume,
   avg_30_day_call_oi, avg_30_day_put_oi, volatility_30, volatility_60,
   implied_move_perc_30, implied_move_perc_60, bullish/bearish_premium.
   Valores numericos vem como **strings** decimais.

2. /api/gex/{ticker}?timespan=1y
   Retorna {"data":[{"date","close","call_gex","put_gex","call_delta",
   "put_delta","call_charm","put_charm","call_vanna","put_vanna"},...]}
   ~1 ponto por dia durante 1 ano.

Persistencia:
- options_flow_daily (UNIQUE(ticker,date))
- gex_daily          (UNIQUE(ticker,date))

Uso:
    from collectors import unusual_whales
    result = unusual_whales.collect()
    # {"status":"ok","tickers":[{"ticker":"PBR","flow_rows":30,
    #   "gex_rows":252}], "flow_upserted":..., "gex_upserted":...}
"""
from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx
import yaml

from storage.db import get_conn

_log = logging.getLogger(__name__)

_REPO_ROOT   = Path(__file__).resolve().parent.parent
_CONFIG_PATH = _REPO_ROOT / "config.yaml"

_FLOW_URL = "https://phx.unusualwhales.com/api/market_state_all/{ticker}?limit=1"
_GEX_URL  = "https://phx.unusualwhales.com/api/gex/{ticker}?timespan=1y"

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Origin": "https://unusualwhales.com",
    "Referer": "https://unusualwhales.com/stock/{ticker}/overview",
}


# ─── helpers puros (testaveis) ──────────────────────────────────────────────

def _to_float(v: Any) -> float | None:
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _to_int(v: Any) -> int | None:
    f = _to_float(v)
    if f is None:
        return None
    try:
        return int(f)
    except (TypeError, ValueError):
        return None


def _safe_div(num: float | None, den: float | None) -> float | None:
    if num is None or den is None or den == 0:
        return None
    return num / den


def parse_market_state(ticker: str, payload: list[dict]) -> list[dict]:
    """Converte array bruto do /market_state_all em rows para options_flow_daily.

    Levanta ValueError se o shape nao bater.
    """
    if not isinstance(payload, list):
        raise ValueError("market_state payload nao eh lista")

    rows: list[dict] = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        date = item.get("date")
        if not isinstance(date, str) or not date:
            continue

        c_vol = _to_int(item.get("call_volume"))
        p_vol = _to_int(item.get("put_volume"))
        volume = (c_vol or 0) + (p_vol or 0) if (c_vol is not None or p_vol is not None) else None
        pc_ratio = _safe_div(
            _to_float(item.get("put_volume")),
            _to_float(item.get("call_volume")),
        )

        c_oi = _to_int(item.get("call_open_interest"))
        p_oi = _to_int(item.get("put_open_interest"))
        total_oi = item.get("total_open_interest")
        total_oi = _to_int(total_oi) if total_oi is not None else (
            (c_oi or 0) + (p_oi or 0) if (c_oi is not None or p_oi is not None) else None
        )

        avg_c_oi = _to_float(item.get("avg_30_day_call_oi"))
        avg_p_oi = _to_float(item.get("avg_30_day_put_oi"))
        avg_oi = (avg_c_oi or 0) + (avg_p_oi or 0) if (avg_c_oi or avg_p_oi) else None
        oi_pct = _safe_div(total_oi, avg_oi) if total_oi is not None and avg_oi else None

        avg_c_vol = _to_float(item.get("avg_30_day_call_volume"))
        avg_p_vol = _to_float(item.get("avg_30_day_put_volume"))
        avg_vol = (avg_c_vol or 0) + (avg_p_vol or 0) if (avg_c_vol or avg_p_vol) else None
        vol_30d_ratio = _safe_div(volume, avg_vol) if volume is not None and avg_vol else None

        close = _to_float(item.get("close"))
        open_ = _to_float(item.get("open"))
        pct_change = _safe_div(
            (close - open_) if (close is not None and open_ is not None) else None,
            open_,
        )

        c_prem = _to_float(item.get("call_premium"))
        p_prem = _to_float(item.get("put_premium"))
        total_prem = (c_prem or 0) + (p_prem or 0) if (c_prem or p_prem) else None

        rows.append({
            "ticker":        ticker,
            "date":          date,
            "open":          open_,
            "high":          _to_float(item.get("high")),
            "low":           _to_float(item.get("low")),
            "close":         close,
            "pct_change":    pct_change,
            "pc_ratio":      pc_ratio,
            "volume":        volume,
            "c_vol":         c_vol,
            "p_vol":         p_vol,
            "vol_30d_ratio": vol_30d_ratio,
            "total_oi":      total_oi,
            "oi_pct":        oi_pct,
            "c_oi":          c_oi,
            "p_oi":          p_oi,
            "ivr":           _to_float(item.get("iv_rank")),
            "vol_30d":       _to_float(item.get("volatility_30")),
            "implied_30d":   _to_float(item.get("implied_move_perc_30")),
            "vol_60d":       _to_float(item.get("volatility_60")),
            "implied_60d":   _to_float(item.get("implied_move_perc_60")),
            "net_prem":      _to_float(item.get("net_premium")),
            "total_prem":    total_prem,
            "source_raw":    json.dumps(item, separators=(",", ":")),
        })
    return rows


def parse_gex(ticker: str, payload: dict) -> list[dict]:
    """Converte payload do /api/gex em rows pra gex_daily."""
    if not isinstance(payload, dict):
        raise ValueError("gex payload nao eh dict")
    data = payload.get("data")
    if not isinstance(data, list):
        raise ValueError("gex payload sem 'data' lista")

    rows: list[dict] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        date = item.get("date")
        if not isinstance(date, str) or not date:
            continue
        rows.append({
            "ticker":     ticker,
            "date":       date,
            "close":      _to_float(item.get("close")),
            "call_gex":   _to_float(item.get("call_gex")),
            "put_gex":    _to_float(item.get("put_gex")),
            "call_delta": _to_float(item.get("call_delta")),
            "put_delta":  _to_float(item.get("put_delta")),
            "call_charm": _to_float(item.get("call_charm")),
            "put_charm":  _to_float(item.get("put_charm")),
            "call_vanna": _to_float(item.get("call_vanna")),
            "put_vanna":  _to_float(item.get("put_vanna")),
        })
    return rows


# ─── I/O ─────────────────────────────────────────────────────────────────────

def _load_config() -> dict:
    cfg = yaml.safe_load(_CONFIG_PATH.read_text(encoding="utf-8"))
    return cfg.get("options_flow", {})


def _headers_for(ticker: str) -> dict:
    h = dict(_HEADERS)
    h["Referer"] = _HEADERS["Referer"].format(ticker=ticker)
    return h


def fetch_flow(ticker: str, timeout: float = 30.0) -> list[dict]:
    r = httpx.get(_FLOW_URL.format(ticker=ticker),
                  headers=_headers_for(ticker), timeout=timeout)
    r.raise_for_status()
    return r.json()


def fetch_gex(ticker: str, timeout: float = 30.0) -> dict:
    r = httpx.get(_GEX_URL.format(ticker=ticker),
                  headers=_headers_for(ticker), timeout=timeout)
    r.raise_for_status()
    return r.json()


def _upsert_flow(rows: list[dict], ts_collected: str) -> int:
    sql = """
        INSERT INTO options_flow_daily
            (ts_collected, ticker, date, open, high, low, close, pct_change,
             pc_ratio, volume, c_vol, p_vol, vol_30d_ratio, total_oi, oi_pct,
             c_oi, p_oi, ivr, vol_30d, implied_30d, vol_60d, implied_60d,
             net_prem, total_prem, source_raw_json)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(ticker, date) DO UPDATE SET
            ts_collected    = excluded.ts_collected,
            open            = excluded.open,
            high            = excluded.high,
            low             = excluded.low,
            close           = excluded.close,
            pct_change      = excluded.pct_change,
            pc_ratio        = excluded.pc_ratio,
            volume          = excluded.volume,
            c_vol           = excluded.c_vol,
            p_vol           = excluded.p_vol,
            vol_30d_ratio   = excluded.vol_30d_ratio,
            total_oi        = excluded.total_oi,
            oi_pct          = excluded.oi_pct,
            c_oi            = excluded.c_oi,
            p_oi            = excluded.p_oi,
            ivr             = excluded.ivr,
            vol_30d         = excluded.vol_30d,
            implied_30d     = excluded.implied_30d,
            vol_60d         = excluded.vol_60d,
            implied_60d     = excluded.implied_60d,
            net_prem        = excluded.net_prem,
            total_prem      = excluded.total_prem,
            source_raw_json = excluded.source_raw_json
    """
    n = 0
    with get_conn() as conn:
        for r in rows:
            conn.execute(sql, (
                ts_collected, r["ticker"], r["date"],
                r.get("open"), r.get("high"), r.get("low"), r.get("close"),
                r.get("pct_change"), r.get("pc_ratio"), r.get("volume"),
                r.get("c_vol"), r.get("p_vol"), r.get("vol_30d_ratio"),
                r.get("total_oi"), r.get("oi_pct"), r.get("c_oi"), r.get("p_oi"),
                r.get("ivr"), r.get("vol_30d"), r.get("implied_30d"),
                r.get("vol_60d"), r.get("implied_60d"),
                r.get("net_prem"), r.get("total_prem"),
                r.get("source_raw"),
            ))
            n += 1
    return n


def _upsert_gex(rows: list[dict], ts_collected: str) -> int:
    sql = """
        INSERT INTO gex_daily
            (ts_collected, ticker, date, close, call_gex, put_gex,
             call_delta, put_delta, call_charm, put_charm,
             call_vanna, put_vanna)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(ticker, date) DO UPDATE SET
            ts_collected = excluded.ts_collected,
            close        = excluded.close,
            call_gex     = excluded.call_gex,
            put_gex      = excluded.put_gex,
            call_delta   = excluded.call_delta,
            put_delta    = excluded.put_delta,
            call_charm   = excluded.call_charm,
            put_charm    = excluded.put_charm,
            call_vanna   = excluded.call_vanna,
            put_vanna    = excluded.put_vanna
    """
    n = 0
    with get_conn() as conn:
        for r in rows:
            conn.execute(sql, (
                ts_collected, r["ticker"], r["date"], r.get("close"),
                r.get("call_gex"), r.get("put_gex"),
                r.get("call_delta"), r.get("put_delta"),
                r.get("call_charm"), r.get("put_charm"),
                r.get("call_vanna"), r.get("put_vanna"),
            ))
            n += 1
    return n


# ─── orchestrator ───────────────────────────────────────────────────────────

def collect(tickers: list[str] | None = None) -> dict[str, Any]:
    cfg = _load_config()
    tickers = tickers or list(cfg.get("tickers") or [])
    if not tickers:
        return {"status": "failed", "error": "config.yaml: options_flow.tickers vazio"}

    timeout = float(cfg.get("request_timeout_s", 30.0))
    delay   = float(cfg.get("request_delay_seconds", 3.0))

    ts_collected = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    per_ticker: list[dict] = []
    flow_upserted = 0
    gex_upserted  = 0
    failed: list[dict] = []

    for i, t in enumerate(tickers):
        if i > 0:
            time.sleep(delay)
        t = t.upper()

        try:
            flow_payload = fetch_flow(t, timeout=timeout)
            flow_rows = parse_market_state(t, flow_payload)
            n_flow = _upsert_flow(flow_rows, ts_collected) if flow_rows else 0
        except Exception as ex:
            _log.exception("flow failed for %s", t)
            failed.append({"ticker": t, "stage": "flow", "error": str(ex)})
            n_flow = 0
            flow_rows = []

        try:
            time.sleep(delay / 2)
            gex_payload = fetch_gex(t, timeout=timeout)
            gex_rows = parse_gex(t, gex_payload)
            n_gex = _upsert_gex(gex_rows, ts_collected) if gex_rows else 0
        except Exception as ex:
            _log.exception("gex failed for %s", t)
            failed.append({"ticker": t, "stage": "gex", "error": str(ex)})
            n_gex = 0

        flow_upserted += n_flow
        gex_upserted  += n_gex
        per_ticker.append({"ticker": t, "flow_rows": n_flow, "gex_rows": n_gex})
        _log.info("uw %s: flow=%d gex=%d", t, n_flow, n_gex)

    if failed and flow_upserted == 0 and gex_upserted == 0:
        status = "failed"
    elif failed:
        status = "partial"
    else:
        status = "ok"

    return {
        "status":        status,
        "tickers":       per_ticker,
        "flow_upserted": flow_upserted,
        "gex_upserted":  gex_upserted,
        "failed":        failed,
    }


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print(json.dumps(collect(), indent=2, default=str))
