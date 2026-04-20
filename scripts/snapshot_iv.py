"""Script diario de snapshot de ATM IV.

Rodado pelo GitHub Action `.github/workflows/iv-snapshot.yml` em cron diario
apos o fechamento de NYSE, e append-o uma linha por ticker em
`data/iv_history.csv`.

Universo: uniao de todos os tickers dos presets em `watchlist_presets.py`,
limitado aos que tem option chain via yfinance.

Uso manual:
    python scripts/snapshot_iv.py                # universo completo
    python scripts/snapshot_iv.py PBR VALE SPY   # tickers especificos
"""

from __future__ import annotations

import os
import sys
from datetime import datetime

# Garante imports do app/
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_APP_DIR    = os.path.abspath(os.path.join(_SCRIPT_DIR, "..", "app"))
sys.path.insert(0, _APP_DIR)

import pandas as pd  # noqa: E402

from services.watchlist_presets import WATCHLIST_PRESETS  # noqa: E402
from services.iv_history_service import (                 # noqa: E402
    append_snapshot,
    compute_atm_iv,
)


def _collect_universe() -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for name, tickers in WATCHLIST_PRESETS.items():
        for t in tickers:
            if t and t not in seen:
                seen.add(t); out.append(t)
    return out


def _fetch_spot_and_chain(ticker: str) -> tuple[float | None, dict | None,
                                                 pd.Series | None]:
    """Busca spot + chain + close history para um ticker.

    Isolado em funcao pra nao importar streamlit (o services/options_service
    ta decorado com @st.cache_data que exige runtime de Streamlit — usamos
    yfinance direto aqui).
    """
    import yfinance as yf

    try:
        tk = yf.Ticker(ticker)
        info_hist = tk.history(period="6mo", auto_adjust=False)
        if info_hist is None or info_hist.empty or "Close" not in info_hist.columns:
            return None, None, None
        spot = float(info_hist["Close"].iloc[-1])
        closes = info_hist["Close"].dropna()
    except Exception as e:
        print(f"  [WARN] {ticker}: history failed: {e}")
        return None, None, None

    # Monta chain no shape esperado por compute_atm_iv
    try:
        expiries = list(tk.options or [])
    except Exception as e:
        print(f"  [WARN] {ticker}: expiries failed: {e}")
        return spot, None, closes

    if not expiries:
        return spot, None, closes

    chain_calls: list[pd.DataFrame] = []
    chain_puts:  list[pd.DataFrame] = []
    for exp in expiries[:6]:
        try:
            oc = tk.option_chain(exp)
        except Exception:
            continue
        # Adiciona daysToExpiry
        days = (datetime.strptime(exp, "%Y-%m-%d").date()
                - datetime.utcnow().date()).days
        days = max(days, 1)
        for side, target in (("calls", oc.calls), ("puts", oc.puts)):
            if target is None or target.empty:
                continue
            d = target.copy()
            for col in ("strike", "impliedVolatility", "openInterest"):
                if col not in d.columns:
                    d[col] = 0.0
            d["daysToExpiry"] = days
            d["expiry"]       = exp
            (chain_calls if side == "calls" else chain_puts).append(d)

    chain = {
        "available": bool(chain_calls or chain_puts),
        "calls":     pd.concat(chain_calls, ignore_index=True) if chain_calls else pd.DataFrame(),
        "puts":      pd.concat(chain_puts,  ignore_index=True) if chain_puts  else pd.DataFrame(),
    }
    return spot, chain, closes


def _compute_hv20(closes: pd.Series) -> float | None:
    """HV20 anualizada (decimal). Ultimo ponto da serie."""
    import numpy as np
    if closes is None or len(closes) < 21:
        return None
    log_ret = (closes / closes.shift(1)).dropna()
    # ln via numpy
    log_ret = log_ret.apply(lambda x: float(__import__("math").log(x)) if x > 0 else 0.0)
    hv = log_ret.rolling(20).std().dropna()
    if hv.empty:
        return None
    return float(hv.iloc[-1]) * (252 ** 0.5)


def main(tickers: list[str] | None = None) -> int:
    universe = tickers or _collect_universe()
    print(f"[snapshot_iv] {len(universe)} tickers: {', '.join(universe)}")
    print(f"[snapshot_iv] utc date: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')}")

    ok = fail = skipped = 0
    for t in universe:
        spot, chain, closes = _fetch_spot_and_chain(t)
        if spot is None:
            print(f"  [SKIP] {t}: sem cotacao")
            skipped += 1
            continue
        atm_iv = compute_atm_iv(chain, spot) if chain else None
        hv20   = _compute_hv20(closes)
        if atm_iv is None and hv20 is None:
            print(f"  [SKIP] {t}: sem IV nem HV utilizaveis")
            skipped += 1
            continue
        try:
            append_snapshot(ticker=t, atm_iv=atm_iv, atm_hv=hv20, spot=spot)
            iv_s = f"{atm_iv*100:.1f}%" if atm_iv else "—"
            hv_s = f"{hv20*100:.1f}%"  if hv20   else "—"
            print(f"  [OK]   {t}: spot={spot:.2f}  iv={iv_s}  hv={hv_s}")
            ok += 1
        except Exception as e:
            print(f"  [FAIL] {t}: {e}")
            fail += 1

    print(f"\n[snapshot_iv] done: ok={ok} fail={fail} skipped={skipped}")
    return 0 if fail == 0 else 1


if __name__ == "__main__":
    args = sys.argv[1:]
    rc = main(args if args else None)
    sys.exit(rc)
