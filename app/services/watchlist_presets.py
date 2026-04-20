"""Watchlist presets — catalogos tematicos para o Thesis Monitor.

Modulo sem I/O e sem matematica: apenas dados estaticos de grupos de tickers.
"Custom" e placeholder populado em sessao pelo usuario (sem persistencia).
"""

from __future__ import annotations


WATCHLIST_PRESETS: dict[str, list[str]] = {
    "Default":       ["PBR", "EWZ", "SPY", "XLE", "USO", "VALE", "BZ=F", "BRL=X", "^VIX"],
    "Energy":        ["XLE", "XOM", "CVX", "BP", "SHEL", "COP", "SLB", "USO", "UNG"],
    "Brasil ADRs":   ["PBR", "VALE", "ITUB", "BBD", "ABEV", "SBS", "EWZ"],
    "Volatility":    ["^VIX", "UVXY", "VXX", "SVIX", "SPY", "QQQ"],
    "Commodities":   ["BZ=F", "CL=F", "GC=F", "SI=F", "HG=F", "USO", "GLD", "SLV"],
    "Mag 7 + Index": ["AAPL", "MSFT", "GOOGL", "AMZN", "META", "NVDA", "TSLA", "SPY", "QQQ"],
    "Financials US": ["XLF", "JPM", "BAC", "WFC", "GS", "MS", "C", "BRK-B"],
    "Custom":        [],  # placeholder, populado via session_state
}


def get_preset(name: str) -> list[str]:
    """Retorna copia da lista de tickers de um preset. Vazio se inexistente."""
    return WATCHLIST_PRESETS.get(name, []).copy()


def get_preset_names() -> list[str]:
    """Nomes de presets disponiveis, na ordem de definicao."""
    return list(WATCHLIST_PRESETS.keys())
