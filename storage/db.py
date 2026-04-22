"""SQLite connection + migrations runner para o Monitor Diario.

Uso:
    from storage.db import get_conn, apply_migrations
    apply_migrations()                # idempotente
    with get_conn() as conn:
        conn.execute("INSERT INTO ...")

Design:
- Uma conexao por call (SQLite serializa writes; curto-vivido evita locks).
- WAL mode: leituras nao bloqueiam writes.
- Timestamps sempre ISO8601 UTC.
- Migrations: SQL files numerados em migrations/, executados em ordem.
  Controle via tabela _schema_migrations.
"""

from __future__ import annotations

import glob
import os
import sqlite3
import logging
from contextlib import contextmanager
from pathlib import Path

import yaml

_log = logging.getLogger(__name__)

_REPO_ROOT      = Path(__file__).resolve().parent.parent
_CONFIG_PATH    = _REPO_ROOT / "config.yaml"
_MIGRATIONS_DIR = Path(__file__).resolve().parent / "migrations"


def _db_path() -> Path:
    """Resolve o caminho do DB a partir do config.yaml."""
    if _CONFIG_PATH.exists():
        cfg = yaml.safe_load(_CONFIG_PATH.read_text(encoding="utf-8"))
        rel = cfg.get("storage", {}).get("db_path", "data/monitor_diario.db")
    else:
        rel = "data/monitor_diario.db"
    return _REPO_ROOT / rel


@contextmanager
def get_conn():
    """Context manager que devolve sqlite3.Connection com WAL + row_factory."""
    path = _db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), isolation_level=None, timeout=30.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA synchronous  = NORMAL")
    try:
        yield conn
    finally:
        conn.close()


def _ensure_migration_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        """CREATE TABLE IF NOT EXISTS _schema_migrations (
               filename   TEXT PRIMARY KEY,
               applied_at TEXT NOT NULL
           )"""
    )


def _applied_migrations(conn: sqlite3.Connection) -> set[str]:
    rows = conn.execute("SELECT filename FROM _schema_migrations").fetchall()
    return {r["filename"] for r in rows}


def apply_migrations() -> list[str]:
    """Aplica migrations novas em ordem alfabetica. Retorna lista do que aplicou."""
    applied = []
    with get_conn() as conn:
        _ensure_migration_table(conn)
        done = _applied_migrations(conn)
        files = sorted(_MIGRATIONS_DIR.glob("*.sql"))
        for f in files:
            name = f.name
            if name in done:
                continue
            sql = f.read_text(encoding="utf-8")
            _log.info("applying migration %s", name)
            conn.executescript(sql)
            conn.execute(
                "INSERT INTO _schema_migrations(filename, applied_at) "
                "VALUES (?, datetime('now'))", (name,)
            )
            applied.append(name)
    return applied


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    applied = apply_migrations()
    if applied:
        print(f"Applied: {applied}")
    else:
        print("Schema up to date.")
    print(f"DB: {_db_path()}")
