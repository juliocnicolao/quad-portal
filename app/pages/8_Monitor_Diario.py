"""Monitor Diario — painel de coleta 2x/dia (08:30 e 18:30 BRT).

Tres secoes em tabs:
    1. Calendario Economico (US + BR, alto impacto)
    2. Options Flow (PBR, TLT, SPY, EWZ — via Unusual Whales sem login)
    3. Truflation (indice diario de inflacao US)

Dados ficam em SQLite (data/monitor_diario.db) alimentado pelo scheduler
standalone (scheduler/runner.py, agendado via Windows Task Scheduler).

Esta pagina apenas LE do DB — nao dispara coletas automaticamente. Botao
"Rodar agora" em cada secao permite trigger manual sob demanda.
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import streamlit as st

# bootstrap paths
_APP_DIR  = Path(__file__).resolve().parent.parent
_REPO_ROOT = _APP_DIR.parent
sys.path.insert(0, str(_APP_DIR))
sys.path.insert(0, str(_REPO_ROOT))

st.set_page_config(page_title="Monitor Diario | QUAD", page_icon="📡",
                   layout="wide", initial_sidebar_state="expanded")

from components.layout import inject_css, render_sidebar, render_footer, page_header  # noqa: E402
from storage.db        import apply_migrations, get_conn                               # noqa: E402

inject_css()
render_sidebar()
page_header("Monitor Diário",
            "Calendário econômico · Options flow · Truflation — coleta 2x/dia")

# Garante schema (idempotente, barato)
try:
    apply_migrations()
except Exception as ex:
    st.error(f"Falha ao inicializar o banco: {ex}")
    st.stop()


# ─────────────────────────────────────────────────────────────────────────────
# Helpers: status global + badges por secao
# ─────────────────────────────────────────────────────────────────────────────

def _last_run() -> dict | None:
    """Ultimo registro de scheduler_runs."""
    with get_conn() as conn:
        row = conn.execute(
            "SELECT id, ts_started, ts_finished, status, sections "
            "FROM scheduler_runs ORDER BY id DESC LIMIT 1"
        ).fetchone()
    if not row:
        return None
    out = dict(row)
    try:
        out["sections"] = json.loads(out["sections"] or "{}")
    except json.JSONDecodeError:
        out["sections"] = {}
    return out


def _age_badge(iso_ts: str | None, stale_hours: float = 13.0) -> str:
    """Badge HTML colorido segundo idade do timestamp (UTC ISO8601).

    13h > janela entre coletas (12h) — se passou dessa marca, ha um ciclo perdido.
    """
    if not iso_ts:
        return ('<span style="background:#555;color:#fff;padding:2px 8px;'
                'border-radius:10px;font-size:0.7rem;">sem dados</span>')
    try:
        if iso_ts.endswith("Z"):
            iso_ts = iso_ts[:-1] + "+00:00"
        t  = datetime.fromisoformat(iso_ts)
        dt = (datetime.now(timezone.utc) - t).total_seconds() / 3600
    except Exception:
        return ('<span style="background:#555;color:#fff;padding:2px 8px;'
                'border-radius:10px;font-size:0.7rem;">ts invalido</span>')
    if dt < stale_hours:
        color, label = "#0a9", f"fresh ({dt:.1f}h)"
    else:
        color, label = "#c84", f"stale ({dt:.1f}h)"
    return (f'<span style="background:{color};color:#fff;padding:2px 8px;'
            f'border-radius:10px;font-size:0.7rem;">{label}</span>')


# ─────────────────────────────────────────────────────────────────────────────
# Header global: ultimo run + botao de trigger manual
# ─────────────────────────────────────────────────────────────────────────────

last = _last_run()
c1, c2, c3 = st.columns([3, 2, 1])
with c1:
    if last:
        st.markdown(
            f"**Última execução** · run `#{last['id']}` · "
            f"{last['ts_started']} → {last['ts_finished'] or '—'} · "
            f"status: **{last['status']}**",
            unsafe_allow_html=True,
        )
    else:
        st.info("Nenhuma execução registrada ainda. Rode o scheduler "
                "(`python -m scheduler.runner`) para popular o banco.")

with c2:
    sec_map = (last or {}).get("sections", {}) if last else {}
    # Badges por secao no header
    badges = []
    for key, label in [("calendar", "📅 Calendário"),
                       ("uw",       "📊 Options"),
                       ("truflation","🌡️ Truflation")]:
        s = sec_map.get(key, "—")
        color = {"ok":"#0a9","partial":"#c84","failed":"#c33",
                 "skipped":"#777","—":"#555"}.get(s, "#555")
        badges.append(
            f'<span style="background:{color};color:#fff;padding:2px 8px;'
            f'border-radius:10px;font-size:0.7rem;margin-right:6px;">{label}: {s}</span>'
        )
    st.markdown(" ".join(badges), unsafe_allow_html=True)

with c3:
    st.button("▶ Rodar agora", disabled=True,
              help="Será habilitado na Fase 5 (scheduler + polish)")

st.markdown("---")


# ─────────────────────────────────────────────────────────────────────────────
# Tabs
# ─────────────────────────────────────────────────────────────────────────────

tab_cal, tab_uw, tab_tru = st.tabs([
    "📅 Calendário econômico",
    "📊 Options flow (UW)",
    "🌡️ Truflation",
])

with tab_cal:
    st.subheader("Calendário econômico (US + BR, alto impacto)")
    st.caption("Fase 3 — CPI, PCE, Payroll, FOMC, IPCA, Copom, etc. "
               "com previsão, anterior, resultado e surpresa.")
    st.info("🚧 Placeholder — implementação na Fase 3.")

with tab_uw:
    st.subheader("Options flow via Unusual Whales")
    st.caption("Fase 4 — PBR, TLT, SPY, EWZ. Net Premium histórico (30d) + "
               "Daily GEX por strike. Scraping sem login; SQLite acumula "
               "histórico próprio para virar série longa em 2-3 meses.")
    st.info("🚧 Placeholder — implementação na Fase 4 (após recon de endpoints).")

with tab_tru:
    st.subheader("Truflation US Inflation Rate")
    st.caption("Fase 2 — valor diário do índice Truflation, delta vs. último "
               "CPI oficial, evolução 60 dias.")
    st.info("🚧 Placeholder — implementação na Fase 2 (primeiro collector real).")


render_footer()
