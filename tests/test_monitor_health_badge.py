"""Testes para _monitor_health_badge — thresholds de alerta no sidebar."""
from __future__ import annotations

import sqlite3
import sys
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest


@pytest.fixture
def _fake_db(tmp_path, monkeypatch):
    """Configura get_conn apontando pra um SQLite temp com scheduler_runs."""
    # importa layout carregando o modulo (path bootstrap)
    APP_DIR = Path(__file__).resolve().parent.parent / "app"
    sys.path.insert(0, str(APP_DIR))

    db = tmp_path / "t.db"
    conn_setup = sqlite3.connect(str(db))
    conn_setup.execute("""CREATE TABLE scheduler_runs(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ts_started TEXT NOT NULL,
        ts_finished TEXT,
        status TEXT NOT NULL,
        sections TEXT NOT NULL,
        notes TEXT
    )""")
    conn_setup.commit()
    conn_setup.close()

    @contextmanager
    def _conn():
        c = sqlite3.connect(str(db))
        c.row_factory = sqlite3.Row
        try:
            yield c
        finally:
            c.close()

    import storage.db as dbmod
    monkeypatch.setattr(dbmod, "get_conn", _conn)

    def _insert(ts_finished: str | None, status: str):
        with _conn() as c:
            c.execute(
                "INSERT INTO scheduler_runs(ts_started,ts_finished,status,sections) "
                "VALUES (?, ?, ?, '{}')",
                ("2026-04-22T00:00:00Z", ts_finished, status),
            )
            c.commit()

    return _insert


def _iso_hours_ago(h: float) -> str:
    return (datetime.now(timezone.utc) - timedelta(hours=h)).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )


def test_no_runs_returns_none(_fake_db):
    from components.layout import _monitor_health_badge
    assert _monitor_health_badge() is None


def test_fresh_ok_run_returns_none(_fake_db):
    from components.layout import _monitor_health_badge
    _fake_db(_iso_hours_ago(3), "ok")
    assert _monitor_health_badge() is None


def test_failed_run_shows_red_badge(_fake_db):
    from components.layout import _monitor_health_badge
    _fake_db(_iso_hours_ago(1), "failed")
    out = _monitor_health_badge()
    assert out is not None
    assert "#c33" in out
    assert "falhou" in out


def test_partial_run_shows_yellow_badge(_fake_db):
    from components.layout import _monitor_health_badge
    _fake_db(_iso_hours_ago(1), "partial")
    out = _monitor_health_badge()
    assert out is not None
    assert "#c84" in out
    assert "parcial" in out.lower()


def test_stale_over_25h_shows_yellow_even_if_ok(_fake_db):
    from components.layout import _monitor_health_badge
    _fake_db(_iso_hours_ago(30), "ok")
    out = _monitor_health_badge()
    assert out is not None
    assert "#c84" in out
    assert "stale" in out.lower()


def test_stale_over_48h_shows_red(_fake_db):
    from components.layout import _monitor_health_badge
    _fake_db(_iso_hours_ago(60), "ok")
    out = _monitor_health_badge()
    assert out is not None
    assert "#c33" in out
    assert "parado" in out.lower()


def test_failed_takes_precedence_over_stale(_fake_db):
    from components.layout import _monitor_health_badge
    # um run falhou ha 60h — deve ser vermelho com msg de falha (nao "parado")
    _fake_db(_iso_hours_ago(60), "failed")
    out = _monitor_health_badge()
    assert out is not None
    assert "falhou" in out
