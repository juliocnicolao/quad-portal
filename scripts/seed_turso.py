"""One-time seed: copia dados do SQLite local pro Turso remoto.

Uso (com env vars TURSO_* ou secrets.toml setados):
    python scripts/seed_turso.py

Le `data/monitor_diario.db` local e insere INSERT OR IGNORE em cada tabela
do Turso. Idempotente: rodar 2x nao duplica (UNIQUE constraints + IGNORE).

Pula _schema_migrations (aplicado via apply_migrations previamente) e
sqlite_sequence (interno).
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import yaml

_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT))

from storage.db import get_conn, is_remote  # noqa: E402


SKIP_TABLES = {"sqlite_sequence", "_schema_migrations"}


def _local_db_path() -> Path:
    cfg = yaml.safe_load((_REPO_ROOT / "config.yaml").read_text(encoding="utf-8"))
    return _REPO_ROOT / cfg["storage"]["db_path"]


def _tables(conn) -> list[str]:
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    ).fetchall()
    return [r[0] for r in rows]


def _columns(conn, table: str) -> list[str]:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return [r[1] for r in rows]


def main() -> int:
    if not is_remote():
        print("ERRO: TURSO_DATABASE_URL / TURSO_AUTH_TOKEN nao setados.")
        print("Configure em .streamlit/secrets.toml ou env vars.")
        return 1

    local_path = _local_db_path()
    if not local_path.exists():
        print(f"ERRO: SQLite local nao encontrado em {local_path}")
        return 1

    print(f"Source: {local_path}")
    print("Target: Turso (remote)")
    print()

    local = sqlite3.connect(str(local_path))
    local.row_factory = sqlite3.Row

    total_rows = 0
    with get_conn() as remote:
        tables = [t for t in _tables(local) if t not in SKIP_TABLES]
        for t in tables:
            cols = _columns(local, t)
            col_list = ", ".join(cols)
            placeholders = ", ".join(["?"] * len(cols))
            sql_ins = f"INSERT OR IGNORE INTO {t} ({col_list}) VALUES ({placeholders})"
            rows = local.execute(f"SELECT {col_list} FROM {t}").fetchall()
            inserted = 0
            for r in rows:
                try:
                    remote.execute(sql_ins, tuple(r))
                    inserted += 1
                except Exception as ex:
                    print(f"  ! {t}: {ex}")
            print(f"  {t:30s} {inserted:>5d} rows")
            total_rows += inserted
        try:
            remote.commit()
        except Exception:
            pass

    local.close()
    print()
    print(f"Total: {total_rows} rows inseridas no Turso.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
