"""Collector: options flow via unusualwhales.com (SEM login).

Implementacao definitiva na Fase 4 (apos recon de endpoints). Stub aqui.
"""
from __future__ import annotations


def collect(tickers: list[str] | None = None) -> dict:
    """Coleta options flow diario + GEX snapshot e persiste.

    Returns:
        dict com { 'status': 'ok'|'partial'|'failed', 'per_ticker': {ticker: status} }
    """
    raise NotImplementedError("Fase 4")
