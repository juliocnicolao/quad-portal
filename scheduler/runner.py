"""Scheduler CLI — executavel pelo Windows Task Scheduler.

Uso:
    python -m scheduler.runner           # roda todas as secoes
    python -m scheduler.runner --only calendar,truflation

Agenda-se no Windows Task Scheduler:
    Program:    C:\\path\\to\\.venv\\Scripts\\python.exe
    Arguments:  -m scheduler.runner
    Start in:   C:\\Users\\julio\\Projetos\\clientes\\market-portal
    Triggers:   Daily, 08:30 and 18:30 (America/Sao_Paulo)

Cada run grava linha em `scheduler_runs` com status por secao. Falha de uma
secao nao aborta as outras — UI mostra badge por secao com timestamp do ultimo
sucesso.
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT))

from storage.db import apply_migrations, get_conn  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
_log = logging.getLogger("scheduler")


SECTIONS = ("calendar", "uw", "truflation")


def _now_utc_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _run_section(name: str) -> str:
    """Invoca o collector correspondente. Retorna 'ok'|'failed'|'skipped'."""
    try:
        if name == "calendar":
            from collectors import economic_calendar as c
        elif name == "uw":
            from collectors import unusual_whales as c
        elif name == "truflation":
            from collectors import truflation as c
        else:
            _log.warning("unknown section %s", name)
            return "skipped"

        result = c.collect()
        status = (result or {}).get("status", "ok")
        _log.info("section %s -> %s", name, status)
        return status
    except NotImplementedError:
        _log.info("section %s — stub (NotImplementedError), skipping", name)
        return "skipped"
    except Exception as ex:
        _log.exception("section %s failed: %s", name, ex)
        return "failed"


def run(sections: list[str]) -> dict:
    apply_migrations()
    ts_started = _now_utc_iso()

    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO scheduler_runs(ts_started, status, sections) "
            "VALUES (?, 'running', '{}')", (ts_started,)
        )
        run_id = cur.lastrowid

    results: dict[str, str] = {}
    for s in sections:
        results[s] = _run_section(s)

    # Status consolidado
    any_failed = any(v == "failed" for v in results.values())
    all_ok     = all(v == "ok" for v in results.values() if v != "skipped")
    if any_failed and all_ok:
        status = "partial"
    elif any_failed:
        status = "failed"
    else:
        status = "ok"

    ts_finished = _now_utc_iso()
    with get_conn() as conn:
        conn.execute(
            "UPDATE scheduler_runs SET ts_finished=?, status=?, sections=? WHERE id=?",
            (ts_finished, status, json.dumps(results), run_id),
        )
    _log.info("run %s finished: %s (%s)", run_id, status, results)
    return {"run_id": run_id, "status": status, "sections": results}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--only",
        help="Comma-separated subset of sections to run (calendar,uw,truflation)",
    )
    args = ap.parse_args()

    if args.only:
        sections = [s.strip() for s in args.only.split(",") if s.strip()]
    else:
        sections = list(SECTIONS)

    result = run(sections)
    print(json.dumps(result, indent=2))
    return 0 if result["status"] in ("ok", "partial") else 1


if __name__ == "__main__":
    sys.exit(main())
