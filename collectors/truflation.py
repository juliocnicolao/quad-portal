"""Collector: Truflation US CPI Inflation Index (TruCPI-US).

Fonte: endpoint publico da marketplace (sem auth), descoberto via recon em
fase 2. Retorna ~365 pontos diarios (1Y), valores em % (ex: 1.758 = 1.758%).
Delay de ~5 dias (plano free da Truflation — suficiente pra monitor macro).

Endpoint shape:
    {
      "labels":   ["YYYY-MM-DD", ...],           # 366 datas
      "datasets": [{"slug": ..., "title": ...,
                    "unit": "%", "data": [1.37, 1.39, ...]}],
      "isTransformedToDaily": true/false
    }

Persistencia: upsert em `truflation_history` (UNIQUE(date)). Calcula deltas
change_1d/7d/30d a partir dos pontos do proprio payload (nao depende do DB).

Uso:
    from collectors import truflation
    result = truflation.collect()
    # {"status": "ok", "rows_upserted": 366, "latest": {"date": "2026-04-22",
    #  "value": 1.758618, "change_1d": -0.01, ...}}
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import httpx
import yaml

from storage.db import get_conn

_log = logging.getLogger(__name__)

_REPO_ROOT   = Path(__file__).resolve().parent.parent
_CONFIG_PATH = _REPO_ROOT / "config.yaml"


def _load_config() -> dict:
    cfg = yaml.safe_load(_CONFIG_PATH.read_text(encoding="utf-8"))
    return cfg.get("truflation", {})


def fetch_raw(api_url: str, timeout: float = 30.0) -> dict:
    """GET no endpoint publico. Sem auth, sem cookie, User-Agent basico."""
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/131.0.0.0 Safari/537.36"
        ),
        "Accept": "application/json, text/plain, */*",
        "Referer": "https://truflation.com/marketplace/us-inflation-rate",
    }
    r = httpx.get(api_url, headers=headers, timeout=timeout)
    r.raise_for_status()
    return r.json()


def parse_payload(payload: dict) -> list[dict]:
    """Converte payload cru em lista de rows pra persistencia.

    Retorna:
        [{"date": "YYYY-MM-DD", "value": float,
          "change_1d": float|None, "change_7d": float|None,
          "change_30d": float|None}, ...]

    Levanta ValueError se o shape do JSON nao bater com o esperado.
    """
    labels = payload.get("labels")
    datasets = payload.get("datasets")
    if not isinstance(labels, list) or not labels:
        raise ValueError("payload sem 'labels'")
    if not isinstance(datasets, list) or not datasets:
        raise ValueError("payload sem 'datasets'")

    ds0 = datasets[0]
    if not isinstance(ds0, dict):
        raise ValueError("datasets[0] nao eh objeto")
    data = ds0.get("data")
    if not isinstance(data, list):
        raise ValueError("datasets[0].data nao eh lista")
    if len(data) != len(labels):
        raise ValueError(
            f"labels ({len(labels)}) e data ({len(data)}) com tamanhos diferentes"
        )

    # pares (date, value), filtrando nulls/invalidos
    pairs: list[tuple[str, float]] = []
    for d, v in zip(labels, data):
        if not isinstance(d, str):
            continue
        if v is None:
            continue
        try:
            pairs.append((d, float(v)))
        except (TypeError, ValueError):
            continue

    # labels ja vem em ordem cronologica crescente, mas garantimos
    pairs.sort(key=lambda p: p[0])

    values_by_date = {d: v for d, v in pairs}
    dates_sorted = [d for d, _ in pairs]
    idx_of = {d: i for i, d in enumerate(dates_sorted)}

    rows: list[dict] = []
    for i, (d, v) in enumerate(pairs):
        row = {"date": d, "value": v,
               "change_1d": None, "change_7d": None, "change_30d": None}
        if i - 1 >= 0:
            row["change_1d"] = v - pairs[i - 1][1]
        if i - 7 >= 0:
            row["change_7d"] = v - pairs[i - 7][1]
        if i - 30 >= 0:
            row["change_30d"] = v - pairs[i - 30][1]
        rows.append(row)

    return rows


def _upsert_rows(rows: list[dict], source_raw: str, ts_collected: str) -> int:
    """Upsert em truflation_history (UNIQUE(date)). Retorna linhas afetadas."""
    sql = """
        INSERT INTO truflation_history
            (ts_collected, date, value, change_1d, change_7d, change_30d, source_raw)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(date) DO UPDATE SET
            ts_collected = excluded.ts_collected,
            value        = excluded.value,
            change_1d    = excluded.change_1d,
            change_7d    = excluded.change_7d,
            change_30d   = excluded.change_30d,
            source_raw   = excluded.source_raw
    """
    count = 0
    with get_conn() as conn:
        for r in rows:
            conn.execute(sql, (
                ts_collected,
                r["date"],
                r["value"],
                r.get("change_1d"),
                r.get("change_7d"),
                r.get("change_30d"),
                source_raw,
            ))
            count += 1
    return count


def collect() -> dict[str, Any]:
    """Coleta full + persiste. Idempotente (safe rodar varias vezes).

    Returns:
        {
          "status": "ok" | "failed",
          "rows_upserted": int,
          "latest": {"date": str, "value": float, "change_1d": float|None, ...},
          "error": str (apenas se failed)
        }
    """
    from datetime import datetime, timezone

    cfg = _load_config()
    api_url = cfg.get("api_url")
    if not api_url:
        return {"status": "failed", "error": "config.yaml: truflation.api_url ausente"}

    timeout = float(cfg.get("request_timeout_s", 30.0))
    ts_collected = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    try:
        payload = fetch_raw(api_url, timeout=timeout)
    except Exception as ex:
        _log.exception("truflation fetch failed")
        return {"status": "failed", "error": f"fetch: {ex}"}

    try:
        rows = parse_payload(payload)
    except Exception as ex:
        _log.exception("truflation parse failed")
        return {"status": "failed", "error": f"parse: {ex}"}

    if not rows:
        return {"status": "failed", "error": "payload parseado vazio"}

    # source_raw: so a URL + contagem (nao salvamos os 365 pts em cada row;
    # bastaria nos ultimos, mas pra simplicidade fica igual em todas).
    source_raw = json.dumps({"url": api_url, "n": len(rows)}, separators=(",", ":"))

    try:
        n = _upsert_rows(rows, source_raw=source_raw, ts_collected=ts_collected)
    except Exception as ex:
        _log.exception("truflation upsert failed")
        return {"status": "failed", "error": f"upsert: {ex}"}

    latest = rows[-1]
    _log.info("truflation ok: %d rows, latest=%s value=%.4f",
              n, latest["date"], latest["value"])
    return {
        "status": "ok",
        "rows_upserted": n,
        "latest": latest,
    }


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print(json.dumps(collect(), indent=2, default=str))
