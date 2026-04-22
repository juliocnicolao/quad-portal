"""SQLite/libSQL connection + migrations runner para o Monitor Diario.

Uso:
    from storage.db import get_conn, apply_migrations
    apply_migrations()                # idempotente
    with get_conn() as conn:
        conn.execute("INSERT INTO ...")

Modos de conexao:
- **Local** (default, dev): sqlite3 apontando para `config.yaml -> storage.db_path`.
- **Remote** (Streamlit Cloud / produ): libSQL (Turso) via env vars
  `TURSO_DATABASE_URL` + `TURSO_AUTH_TOKEN`. Tambem le de `st.secrets` se
  estiver rodando sob Streamlit.

A API publica (`get_conn`, `apply_migrations`, `is_remote`) eh idemptica nos
dois modos. A diferenca interna:
- Remote ignora PRAGMAs que nao fazem sentido (WAL, synchronous).
- Remote nao suporta `VACUUM INTO` (scheduler pula backup local nesse modo).

Design:
- Uma conexao por call (SQLite serializa writes; curto-vivido evita locks).
- WAL mode local: leituras nao bloqueiam writes.
- Timestamps sempre ISO8601 UTC.
- Migrations: SQL files numerados em migrations/, executados em ordem.
  Controle via tabela _schema_migrations.
"""

from __future__ import annotations

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


# ─── resolucao de credenciais / modo ────────────────────────────────────────

def _turso_creds() -> tuple[str | None, str | None]:
    """Le TURSO_DATABASE_URL + TURSO_AUTH_TOKEN de env ou st.secrets."""
    url = os.environ.get("TURSO_DATABASE_URL")
    tok = os.environ.get("TURSO_AUTH_TOKEN")
    if url and tok:
        return url, tok
    # fallback: streamlit secrets — so se streamlit ja esta importado
    # (evita trigger de CSRF warning quando rodado via CLI puro).
    import sys as _sys
    if "streamlit" in _sys.modules:
        try:
            st = _sys.modules["streamlit"]
            sec = st.secrets
            url = url or sec.get("TURSO_DATABASE_URL")
            tok = tok or sec.get("TURSO_AUTH_TOKEN")
        except Exception:
            pass
    return url, tok


def is_remote() -> bool:
    """True se env vars Turso estao setadas (modo remoto)."""
    url, tok = _turso_creds()
    return bool(url and tok)


def _db_path() -> Path:
    """Resolve o caminho do DB local a partir do config.yaml."""
    if _CONFIG_PATH.exists():
        cfg = yaml.safe_load(_CONFIG_PATH.read_text(encoding="utf-8"))
        rel = cfg.get("storage", {}).get("db_path", "data/monitor_diario.db")
    else:
        rel = "data/monitor_diario.db"
    return _REPO_ROOT / rel


# ─── connection factory ─────────────────────────────────────────────────────

@contextmanager
def get_conn():
    """Context manager que devolve conexao pronta pra uso.

    Remote: libsql_experimental.connect(url, auth_token).
    Local:  sqlite3.connect com WAL + row_factory.
    """
    url, tok = _turso_creds()
    if url and tok:
        try:
            import libsql_experimental as libsql  # type: ignore
        except ImportError as ex:
            raise RuntimeError(
                "TURSO_DATABASE_URL set but libsql-experimental not installed. "
                "Run: pip install libsql-experimental"
            ) from ex
        conn = libsql.connect(database=url, auth_token=tok)
        try:
            yield conn
        finally:
            try:
                conn.commit()
            except Exception:
                pass
            # libsql_experimental nao tem close() explicito em versoes antigas
            try:
                conn.close()
            except Exception:
                pass
        return

    # ── local sqlite3 ──
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


# ─── migrations ─────────────────────────────────────────────────────────────

def _ensure_migration_table(conn) -> None:
    conn.execute(
        """CREATE TABLE IF NOT EXISTS _schema_migrations (
               filename   TEXT PRIMARY KEY,
               applied_at TEXT NOT NULL
           )"""
    )


def _applied_migrations(conn) -> set[str]:
    rows = conn.execute("SELECT filename FROM _schema_migrations").fetchall()
    out = set()
    for r in rows:
        # sqlite3.Row suporta r["filename"]; libsql retorna tuple
        try:
            out.add(r["filename"])
        except (TypeError, IndexError, KeyError):
            out.add(r[0])
    return out


def _exec_script(conn, sql: str) -> None:
    """Executa um script SQL multi-statement.

    sqlite3 tem executescript(); libsql_experimental nao. Fallback:
    split por ';' e executa cada statement nao-vazio.
    """
    if hasattr(conn, "executescript"):
        try:
            conn.executescript(sql)
            return
        except Exception:
            pass
    # fallback: split manual. Nao lida com ';' dentro de strings — migrations
    # do projeto sao CREATE TABLE/INDEX simples, sem strings com ';'.
    for stmt in sql.split(";"):
        s = stmt.strip()
        if s:
            conn.execute(s)


def apply_migrations() -> list[str]:
    """Aplica migrations novas em ordem alfabetica. Retorna lista do que aplicou."""
    applied: list[str] = []
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
            _exec_script(conn, sql)
            conn.execute(
                "INSERT INTO _schema_migrations(filename, applied_at) "
                "VALUES (?, datetime('now'))", (name,)
            )
            applied.append(name)
        try:
            conn.commit()
        except Exception:
            pass
    return applied


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    mode = "remote (Turso)" if is_remote() else f"local ({_db_path()})"
    print(f"Mode: {mode}")
    applied = apply_migrations()
    if applied:
        print(f"Applied: {applied}")
    else:
        print("Schema up to date.")
