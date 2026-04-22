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

import yaml

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


def _run_section(name: str) -> tuple[str, dict]:
    """Invoca o collector. Retorna (status, full_result_dict).

    `full_result_dict` carrega events_failed/tickers/etc. pra serializar
    em scheduler_runs.notes. Status eh 'ok'|'partial'|'failed'|'skipped'.
    """
    try:
        if name == "calendar":
            from collectors import economic_calendar as c
        elif name == "uw":
            from collectors import unusual_whales as c
        elif name == "truflation":
            from collectors import truflation as c
        else:
            _log.warning("unknown section %s", name)
            return "skipped", {}

        result = c.collect() or {}
        status = result.get("status", "ok")
        _log.info("section %s -> %s", name, status)
        return status, result
    except NotImplementedError:
        _log.info("section %s — stub (NotImplementedError), skipping", name)
        return "skipped", {}
    except Exception as ex:
        _log.exception("section %s failed: %s", name, ex)
        return "failed", {"error": str(ex)[:300]}


def _rotate_logs(retention_days: int = 14) -> None:
    """Rotate `logs/scheduler_run.log` se ele tiver >retention_days dias.

    Simples: se o arquivo existe e a mtime eh mais velha que retention_days,
    move pra scheduler_run.log.YYYY-MM-DD e recomeca. Alem disso, apaga
    rotated logs mais velhos que retention_days.
    """
    from datetime import date, timedelta
    logs_dir = _REPO_ROOT / "logs"
    if not logs_dir.exists():
        return
    active = logs_dir / "scheduler_run.log"
    today = date.today()
    cutoff = today - timedelta(days=retention_days)

    # Rotate ativo se mtime for de ontem ou mais velho
    if active.exists():
        mtime_date = datetime.fromtimestamp(active.stat().st_mtime).date()
        if mtime_date < today:
            rotated = logs_dir / f"scheduler_run.log.{mtime_date.isoformat()}"
            try:
                if not rotated.exists():
                    active.rename(rotated)
                else:
                    # ja existe (day wrap com 2 runs): append + truncate
                    rotated.write_bytes(rotated.read_bytes() + active.read_bytes())
                    active.write_bytes(b"")
            except OSError as ex:
                _log.warning("log rotate failed: %s", ex)

    # Apaga logs mais velhos que retention
    for p in logs_dir.glob("scheduler_run.log.*"):
        try:
            suffix = p.name.rsplit(".", 1)[-1]  # YYYY-MM-DD
            y, m, d = (int(x) for x in suffix.split("-"))
            if date(y, m, d) < cutoff:
                p.unlink()
                _log.info("rotated log removed: %s", p.name)
        except (ValueError, OSError):
            continue


def _retention_days_from_config() -> int:
    try:
        cfg_path = _REPO_ROOT / "config.yaml"
        cfg = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
        return int(cfg.get("logging", {}).get("retention_days", 14))
    except Exception:
        return 14


def _vacuum_scheduler_runs(keep_last: int = 200) -> None:
    """Mantem so os ultimos N registros de scheduler_runs."""
    with get_conn() as conn:
        conn.execute(
            "DELETE FROM scheduler_runs WHERE id NOT IN "
            "(SELECT id FROM scheduler_runs ORDER BY id DESC LIMIT ?)",
            (keep_last,),
        )


def _backup_db(retention_days: int = 14) -> Path | None:
    """Snapshot diario do SQLite via `VACUUM INTO`.

    Cria data/backups/monitor_diario-YYYY-MM-DD.db. Se ja existe pro dia,
    faz nada (idempotente por dia). Apaga backups mais velhos que
    retention_days. Retorna o path do backup criado ou None.
    """
    from datetime import date, timedelta
    import yaml as _yaml

    cfg_path = _REPO_ROOT / "config.yaml"
    db_rel = "data/monitor_diario.db"
    try:
        cfg = _yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
        db_rel = cfg.get("storage", {}).get("db_path", db_rel)
    except Exception:
        pass
    db_path = _REPO_ROOT / db_rel
    if not db_path.exists():
        return None

    backups_dir = db_path.parent / "backups"
    backups_dir.mkdir(parents=True, exist_ok=True)
    today = date.today()
    target = backups_dir / f"{db_path.stem}-{today.isoformat()}.db"

    created: Path | None = None
    if not target.exists():
        try:
            with get_conn() as conn:
                conn.execute(f"VACUUM INTO '{target.as_posix()}'")
            created = target
            _log.info("db backup written: %s", target.name)
        except Exception as ex:
            _log.warning("db backup failed: %s", ex)

    # Retencao
    cutoff = today - timedelta(days=retention_days)
    prefix = f"{db_path.stem}-"
    for p in backups_dir.glob(f"{prefix}*.db"):
        try:
            suffix = p.stem[len(prefix):]
            y, m, d = (int(x) for x in suffix.split("-"))
            if date(y, m, d) < cutoff:
                p.unlink()
                _log.info("old backup removed: %s", p.name)
        except (ValueError, OSError):
            continue
    return created


def run(sections: list[str]) -> dict:
    apply_migrations()
    _rotate_logs(_retention_days_from_config())
    _backup_db(retention_days=_retention_days_from_config())
    ts_started = _now_utc_iso()

    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO scheduler_runs(ts_started, status, sections) "
            "VALUES (?, 'running', '{}')", (ts_started,)
        )
        run_id = cur.lastrowid

    results: dict[str, str] = {}
    details: dict[str, dict] = {}
    for s in sections:
        st, det = _run_section(s)
        results[s] = st
        details[s] = det

    # Status consolidado. "partial" = ao menos um OK e ao menos um falhou/parcial.
    has_failed   = any(v == "failed"  for v in results.values())
    has_partial  = any(v == "partial" for v in results.values())
    has_ok       = any(v == "ok"      for v in results.values())
    if has_failed and not has_ok:
        status = "failed"
    elif has_failed or has_partial:
        status = "partial"
    else:
        status = "ok"

    # notes: JSON compacto com eventos/tickers que falharam por secao
    notes_payload = {}
    for s, det in details.items():
        if not det:
            continue
        ef = det.get("events_failed") or det.get("failed")
        if ef:
            notes_payload[s] = {"failed": ef}
        elif det.get("error"):
            notes_payload[s] = {"error": det["error"]}
    notes_json = json.dumps(notes_payload, ensure_ascii=False) if notes_payload else None

    ts_finished = _now_utc_iso()
    with get_conn() as conn:
        conn.execute(
            "UPDATE scheduler_runs SET ts_finished=?, status=?, sections=?, notes=? "
            "WHERE id=?",
            (ts_finished, status, json.dumps(results), notes_json, run_id),
        )
    _vacuum_scheduler_runs(keep_last=200)
    _log.info("run %s finished: %s (%s)", run_id, status, results)
    return {"run_id": run_id, "status": status, "sections": results,
            "notes": notes_payload}


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
