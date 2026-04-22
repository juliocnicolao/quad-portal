"""Tests para hardening do scheduler.runner: log rotation + vacuum."""
from __future__ import annotations

import os
import sqlite3
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest

from scheduler import runner


# ─── log rotation ───────────────────────────────────────────────────────────

def _touch_with_mtime(path: Path, days_ago: int) -> None:
    path.write_text("dummy", encoding="utf-8")
    ts = (datetime.now() - timedelta(days=days_ago)).timestamp()
    os.utime(path, (ts, ts))


def test_rotate_logs_creates_dated_file_when_active_is_old(tmp_path, monkeypatch):
    logs = tmp_path / "logs"
    logs.mkdir()
    active = logs / "scheduler_run.log"
    _touch_with_mtime(active, days_ago=2)

    monkeypatch.setattr(runner, "_REPO_ROOT", tmp_path)
    runner._rotate_logs(retention_days=14)

    # active foi esvaziado ou movido; deve existir um .YYYY-MM-DD
    rotated = list(logs.glob("scheduler_run.log.*"))
    assert len(rotated) == 1
    assert rotated[0].name.startswith("scheduler_run.log.")


def test_rotate_logs_removes_old_rotated(tmp_path, monkeypatch):
    logs = tmp_path / "logs"
    logs.mkdir()
    old_date = (date.today() - timedelta(days=30)).isoformat()
    old = logs / f"scheduler_run.log.{old_date}"
    old.write_text("old log", encoding="utf-8")

    monkeypatch.setattr(runner, "_REPO_ROOT", tmp_path)
    runner._rotate_logs(retention_days=14)

    assert not old.exists()


def test_rotate_logs_keeps_recent_rotated(tmp_path, monkeypatch):
    logs = tmp_path / "logs"
    logs.mkdir()
    recent_date = (date.today() - timedelta(days=3)).isoformat()
    recent = logs / f"scheduler_run.log.{recent_date}"
    recent.write_text("recent", encoding="utf-8")

    monkeypatch.setattr(runner, "_REPO_ROOT", tmp_path)
    runner._rotate_logs(retention_days=14)

    assert recent.exists()


def test_rotate_logs_ignores_missing_dir(tmp_path, monkeypatch):
    # nao cria logs/ de proposito
    monkeypatch.setattr(runner, "_REPO_ROOT", tmp_path)
    runner._rotate_logs(retention_days=14)  # nao deve levantar


def test_rotate_logs_ignores_weird_filenames(tmp_path, monkeypatch):
    logs = tmp_path / "logs"
    logs.mkdir()
    weird = logs / "scheduler_run.log.notadate"
    weird.write_text("x", encoding="utf-8")

    monkeypatch.setattr(runner, "_REPO_ROOT", tmp_path)
    runner._rotate_logs(retention_days=14)

    assert weird.exists()  # nao removeu nem crashou


# ─── vacuum scheduler_runs ──────────────────────────────────────────────────

def test_vacuum_keeps_only_last_n(tmp_path, monkeypatch):
    db = tmp_path / "test.db"

    # monkeypatch get_conn pra apontar pro db temp
    import storage.db as dbmod
    from contextlib import contextmanager

    @contextmanager
    def _fake_conn():
        conn = sqlite3.connect(str(db), isolation_level=None)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()

    monkeypatch.setattr(runner, "get_conn", _fake_conn)

    # cria schema minimo
    with _fake_conn() as c:
        c.execute("""CREATE TABLE scheduler_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts_started TEXT NOT NULL,
            ts_finished TEXT,
            status TEXT NOT NULL,
            sections TEXT NOT NULL,
            notes TEXT
        )""")
        for i in range(20):
            c.execute(
                "INSERT INTO scheduler_runs(ts_started,status,sections) VALUES (?,?,?)",
                (f"2026-01-{i+1:02d}T00:00:00Z", "ok", "{}"),
            )

    runner._vacuum_scheduler_runs(keep_last=5)

    with _fake_conn() as c:
        n = c.execute("SELECT COUNT(*) FROM scheduler_runs").fetchone()[0]
        assert n == 5
        ids = [r[0] for r in c.execute("SELECT id FROM scheduler_runs ORDER BY id").fetchall()]
        assert ids == [16, 17, 18, 19, 20]  # ultimos 5


def test_retention_days_reads_config(tmp_path, monkeypatch):
    cfg = tmp_path / "config.yaml"
    cfg.write_text("logging:\n  retention_days: 7\n", encoding="utf-8")
    monkeypatch.setattr(runner, "_REPO_ROOT", tmp_path)
    assert runner._retention_days_from_config() == 7


def test_retention_days_fallback_when_config_missing(tmp_path, monkeypatch):
    # sem config.yaml
    monkeypatch.setattr(runner, "_REPO_ROOT", tmp_path)
    assert runner._retention_days_from_config() == 14


# ─── db backup ──────────────────────────────────────────────────────────────

def test_backup_db_creates_vacuumed_copy(tmp_path, monkeypatch):
    # Setup: pequeno DB real + config.yaml + mock de get_conn
    (tmp_path / "data").mkdir()
    db_path = tmp_path / "data" / "monitor_diario.db"
    c = sqlite3.connect(str(db_path))
    c.execute("CREATE TABLE t(x INTEGER)")
    c.execute("INSERT INTO t VALUES (1),(2),(3)")
    c.commit()
    c.close()
    (tmp_path / "config.yaml").write_text(
        'storage:\n  db_path: "data/monitor_diario.db"\n', encoding="utf-8"
    )

    from contextlib import contextmanager

    @contextmanager
    def _conn():
        cc = sqlite3.connect(str(db_path), isolation_level=None)
        try:
            yield cc
        finally:
            cc.close()

    monkeypatch.setattr(runner, "_REPO_ROOT", tmp_path)
    monkeypatch.setattr(runner, "get_conn", _conn)
    monkeypatch.setattr(runner, "is_remote", lambda: False)

    out = runner._backup_db(retention_days=14)
    assert out is not None
    assert out.exists()
    assert out.name.startswith("monitor_diario-")
    # segundo call no mesmo dia: idempotente (retorna None, arquivo nao muda)
    out2 = runner._backup_db(retention_days=14)
    assert out2 is None


def test_backup_db_removes_old(tmp_path, monkeypatch):
    (tmp_path / "data").mkdir()
    db_path = tmp_path / "data" / "monitor_diario.db"
    sqlite3.connect(str(db_path)).close()
    (tmp_path / "config.yaml").write_text(
        'storage:\n  db_path: "data/monitor_diario.db"\n', encoding="utf-8"
    )
    # simula backup antigo
    backups = tmp_path / "data" / "backups"
    backups.mkdir()
    old_date = (date.today() - timedelta(days=30)).isoformat()
    old = backups / f"monitor_diario-{old_date}.db"
    old.write_bytes(b"dummy")

    from contextlib import contextmanager

    @contextmanager
    def _conn():
        cc = sqlite3.connect(str(db_path), isolation_level=None)
        try:
            yield cc
        finally:
            cc.close()

    monkeypatch.setattr(runner, "_REPO_ROOT", tmp_path)
    monkeypatch.setattr(runner, "get_conn", _conn)
    monkeypatch.setattr(runner, "is_remote", lambda: False)

    runner._backup_db(retention_days=14)
    assert not old.exists()


def test_backup_db_handles_missing_db(tmp_path, monkeypatch):
    # nao cria data/monitor_diario.db
    monkeypatch.setattr(runner, "_REPO_ROOT", tmp_path)
    monkeypatch.setattr(runner, "is_remote", lambda: False)
    out = runner._backup_db(retention_days=14)
    assert out is None  # silencioso, sem crash


def test_backup_db_skipped_when_remote(tmp_path, monkeypatch):
    monkeypatch.setattr(runner, "_REPO_ROOT", tmp_path)
    monkeypatch.setattr(runner, "is_remote", lambda: True)
    out = runner._backup_db(retention_days=14)
    assert out is None  # no-op em modo remoto
