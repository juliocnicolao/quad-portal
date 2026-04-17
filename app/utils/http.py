"""Shared HTTP helpers: retry/backoff, padrão de User-Agent, timeout.

Uso:
    from utils.http import get_json, get_text
    data = get_json("https://api...", retries=2)
"""
from __future__ import annotations

import time
import requests
from typing import Any

from utils.logger import get_logger

_log = get_logger(__name__)

DEFAULT_UA      = "Mozilla/5.0 (QUAD-Portal)"
DEFAULT_TIMEOUT = 15


def _sleep_backoff(attempt: int) -> None:
    # 0.5s, 1.5s, 3.5s
    time.sleep(0.5 * (2 ** attempt))


def request(
    method: str,
    url: str,
    *,
    retries: int = 2,
    timeout: int = DEFAULT_TIMEOUT,
    headers: dict | None = None,
    **kwargs,
) -> requests.Response | None:
    """HTTP request com retry + backoff exponencial. Retorna None se falhar tudo.

    Não levanta exceção — callers devem checar `None`. Log estruturado
    no logger do módulo."""
    h = {"User-Agent": DEFAULT_UA}
    if headers:
        h.update(headers)

    last_exc: Exception | None = None
    for attempt in range(retries + 1):
        try:
            r = requests.request(method, url, timeout=timeout, headers=h, **kwargs)
            if r.status_code == 429 or 500 <= r.status_code < 600:
                _log.warning("http %s %s -> %d (attempt %d)",
                             method, url, r.status_code, attempt + 1)
                if attempt < retries:
                    _sleep_backoff(attempt)
                    continue
                return None
            r.raise_for_status()
            return r
        except requests.RequestException as e:
            last_exc = e
            _log.warning("http %s %s failed: %s (attempt %d)",
                         method, url, e, attempt + 1)
            if attempt < retries:
                _sleep_backoff(attempt)
                continue
    _log.error("http %s %s esgotou retries: %s", method, url, last_exc)
    return None


def get_json(url: str, **kwargs) -> Any | None:
    r = request("GET", url, **kwargs)
    if r is None:
        return None
    try:
        return r.json()
    except ValueError:
        _log.error("resposta nao-JSON de %s", url)
        return None


def get_text(url: str, **kwargs) -> str | None:
    r = request("GET", url, **kwargs)
    return r.text if r is not None else None


def get_bytes(url: str, **kwargs) -> bytes | None:
    r = request("GET", url, **kwargs)
    return r.content if r is not None else None
