"""AwesomeAPI service — FX rates against BRL (free, no key required)."""

import streamlit as st
from utils import CACHE_TTL
from utils.http import get_json
from utils.logger import get_logger

_log = get_logger(__name__)

_BASE = "https://economia.awesomeapi.com.br/last"

# Pairs: {label: awesome_pair_code}
FX_PAIRS = {
    "Dólar (USD)":   "USD-BRL",
    "Euro (EUR)":    "EUR-BRL",
    "Libra (GBP)":   "GBP-BRL",
    "Franco SUI":    "CHF-BRL",
    "Iene (JPY)":    "JPY-BRL",
    "Dólar CAN":     "CAD-BRL",
    "Dólar AUS":     "AUD-BRL",
    "Yuan (CNY)":    "CNY-BRL",
    "Peso ARG":      "ARS-BRL",
    "BRL → ARS":     "BRL-ARS",
    "BRL → PYG":     "BRL-PYG",
    "BRL → UYU":     "BRL-UYU",
}


def _parse_pair_data(data: dict) -> dict[str, dict]:
    """Converte resposta AwesomeAPI em {'CODE-CODEIN': {...}}."""
    out = {}
    for code, v in data.items():
        try:
            bid = float(v["bid"])
            ask = float(v.get("ask", v["bid"]))
            pct = float(v.get("pctChange", 0))
            out[v["code"] + "-" + v["codein"]] = {
                "bid":        bid,
                "ask":        ask,
                "mid":        (bid + ask) / 2,
                "change_pct": pct,
                "name":       v.get("name", code),
                "error":      False,
            }
        except Exception:
            out[code] = {"error": True}
    return out


@st.cache_data(ttl=CACHE_TTL)
def get_fx(pairs: list[str] | None = None) -> dict[str, dict]:
    """
    Fetch FX rates. Try bulk first; on failure, fetch pair-by-pair so that
    one invalid pair doesn't break the whole response.
    """
    if pairs is None:
        pairs = list(FX_PAIRS.values())

    # 1) Bulk
    try:
        data = get_json(f"{_BASE}/{','.join(pairs)}", timeout=15, retries=1)
        if data:
            out = _parse_pair_data(data)
            # Se conseguiu todos, retorna; senão cai no per-pair para os faltantes
            missing = [p for p in pairs if p not in out or out[p].get("error")]
            if not missing:
                return out
        else:
            out = {}
            missing = list(pairs)
    except Exception as e:
        _log.exception("AwesomeAPI bulk falhou: %s", e)
        out, missing = {}, list(pairs)

    # 2) Per-pair fallback para os que faltaram
    for p in missing:
        try:
            d = get_json(f"{_BASE}/{p}", timeout=8, retries=1)
            if d:
                parsed = _parse_pair_data(d)
                if parsed:
                    # primeiro valor parseado
                    first_key = next(iter(parsed))
                    out[p] = parsed[first_key]
                    continue
        except Exception:
            pass
        out[p] = {"error": True}

    return out
