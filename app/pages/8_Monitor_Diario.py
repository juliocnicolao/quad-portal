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
    st.subheader("Calendário econômico (US + BR)")
    st.caption("Fonte: investing.com · próximos 14 dias · últimos 30 dias. "
               "Surpresa = Actual − Forecast (verde = surpresa positiva para a moeda).")

    import pandas as pd

    with get_conn() as _conn:
        _rows = _conn.execute(
            "SELECT event_time, country, event_name, impact, "
            "       forecast, previous, actual, surprise, surprise_pct, "
            "       unit, source, ts_collected "
            "FROM economic_events ORDER BY event_time ASC"
        ).fetchall()

    if not _rows:
        st.warning("Sem dados do calendário no banco ainda.")
        if st.button("🔄 Coletar agora", key="cal_first_run"):
            from collectors import economic_calendar as _c
            with st.spinner("Buscando calendário (~60-90s, passa por Cloudflare)..."):
                _res = _c.collect()
            if _res.get("status") in ("ok", "partial"):
                st.success(f"OK — {_res['occurrences_upserted']} ocorrências "
                           f"({_res['events_fetched']}/{_res['events_configured']} "
                           f"eventos).")
                st.rerun()
            else:
                st.error(f"Falha: primeira falha = "
                         f"{_res.get('events_failed', [{}])[0].get('error','?')}")
    else:
        df = pd.DataFrame([dict(r) for r in _rows])
        df["event_time"] = pd.to_datetime(df["event_time"], utc=True)
        # converte pra SP p/ exibir
        df["event_local"] = df["event_time"].dt.tz_convert("America/Sao_Paulo")

        from datetime import datetime, timezone, timedelta
        _now = datetime.now(timezone.utc)

        # split: futuros (>= now) vs passados (< now)
        future = df[df["event_time"] >= pd.Timestamp(_now)].copy()
        past   = df[df["event_time"] <  pd.Timestamp(_now)].copy()

        # formatadores
        def _fmt_num(x, unit=None):
            if x is None or pd.isna(x):
                return "—"
            s = f"{x:+.2f}" if unit == "%" else f"{x:.2f}"
            return f"{s}{unit or ''}" if unit == "%" else f"{s}"

        def _color_surprise(v):
            if v is None or pd.isna(v):
                return ""
            if v > 0.05:  return "color: #0a9; font-weight: 600;"
            if v < -0.05: return "color: #c33; font-weight: 600;"
            return "color: #888;"

        st.markdown("### 📅 Próximos eventos (14 dias)")
        if future.empty:
            st.caption("Nenhum evento agendado na janela.")
        else:
            vf = future.sort_values("event_time").head(40).copy()
            vf["Quando"]   = vf["event_local"].dt.strftime("%a %d/%b %H:%M")
            vf["País"]     = vf["country"]
            vf["Evento"]   = vf["event_name"]
            vf["Impacto"]  = vf["impact"].str.upper().map(
                {"HIGH":"🔴 HIGH", "MEDIUM":"🟡 MED", "LOW":"⚪ LOW"}).fillna(vf["impact"])
            vf["Previsão"] = vf.apply(lambda r: _fmt_num(r["forecast"], r["unit"]), axis=1)
            vf["Anterior"] = vf.apply(lambda r: _fmt_num(r["previous"], r["unit"]), axis=1)
            st.dataframe(
                vf[["Quando","País","Evento","Impacto","Previsão","Anterior"]],
                hide_index=True, use_container_width=True, height=min(40*len(vf)+40, 420),
            )

        st.markdown("### 📰 Últimos releases (30 dias)")
        if past.empty:
            st.caption("Nenhum release recente.")
        else:
            vp = past.sort_values("event_time", ascending=False).head(40).copy()
            vp["Quando"]   = vp["event_local"].dt.strftime("%a %d/%b %H:%M")
            vp["País"]     = vp["country"]
            vp["Evento"]   = vp["event_name"]
            vp["Impacto"]  = vp["impact"].str.upper().map(
                {"HIGH":"🔴 HIGH", "MEDIUM":"🟡 MED", "LOW":"⚪ LOW"}).fillna(vp["impact"])
            vp["Actual"]   = vp.apply(lambda r: _fmt_num(r["actual"], r["unit"]), axis=1)
            vp["Previsão"] = vp.apply(lambda r: _fmt_num(r["forecast"], r["unit"]), axis=1)
            vp["Anterior"] = vp.apply(lambda r: _fmt_num(r["previous"], r["unit"]), axis=1)
            vp["Surpresa"] = vp["surprise"].apply(
                lambda x: "—" if x is None or pd.isna(x) else f"{x:+.2f}")
            styled = vp[["Quando","País","Evento","Impacto","Actual","Previsão","Anterior","Surpresa"]]\
                .style.map(_color_surprise, subset=["Surpresa"])
            st.dataframe(styled, hide_index=True, use_container_width=True,
                         height=min(40*len(vp)+40, 420))

        col_refresh, _ = st.columns([1, 5])
        with col_refresh:
            if st.button("🔄 Re-coletar agora", key="cal_rerun"):
                from collectors import economic_calendar as _c
                with st.spinner("Atualizando calendário..."):
                    _res = _c.collect()
                if _res.get("status") in ("ok", "partial"):
                    st.success(f"OK — {_res['occurrences_upserted']} ocorrências "
                               f"({_res['events_fetched']}/{_res['events_configured']} "
                               f"eventos).")
                    st.rerun()
                else:
                    st.error("Falha — veja logs.")

with tab_uw:
    st.subheader("Options flow via Unusual Whales")
    st.caption("Fase 4 — PBR, TLT, SPY, EWZ. Net Premium histórico (30d) + "
               "Daily GEX por strike. Scraping sem login; SQLite acumula "
               "histórico próprio para virar série longa em 2-3 meses.")
    st.info("🚧 Placeholder — implementação na Fase 4 (após recon de endpoints).")

with tab_tru:
    st.subheader("Truflation US CPI Inflation Index")
    st.caption("Índice diário (YoY%) da Truflation — TruCPI-US. "
               "Dados com ~5 dias de delay (plano free). "
               "Fonte: truflation.com/marketplace/us-inflation-rate")

    # Le historico do DB (populado pelo scheduler ou pela run_now abaixo).
    import pandas as pd
    import plotly.graph_objects as go

    with get_conn() as _conn:
        _rows = _conn.execute(
            "SELECT date, value, change_1d, change_7d, change_30d, ts_collected "
            "FROM truflation_history ORDER BY date ASC"
        ).fetchall()

    if not _rows:
        st.warning("Ainda não há dados de Truflation no banco.")
        col_run1, col_run2 = st.columns([1, 5])
        with col_run1:
            if st.button("🔄 Coletar agora", key="tru_first_run"):
                from collectors import truflation as _t
                with st.spinner("Buscando dados da Truflation..."):
                    _res = _t.collect()
                if _res.get("status") == "ok":
                    st.success(f"OK — {_res['rows_upserted']} pontos carregados.")
                    st.rerun()
                else:
                    st.error(f"Falha: {_res.get('error', 'erro desconhecido')}")
    else:
        df = pd.DataFrame([dict(r) for r in _rows])
        df["date"] = pd.to_datetime(df["date"])

        latest = df.iloc[-1]
        ts_coll = latest["ts_collected"]

        # Cards: valor atual + deltas
        c_val, c_1d, c_7d, c_30d, c_age = st.columns([2, 1, 1, 1, 2])
        c_val.metric("Valor atual (YoY %)",
                     f"{latest['value']:.2f}%",
                     delta=(f"{latest['change_1d']:+.3f} pp"
                            if latest["change_1d"] is not None else None))
        c_1d.metric("Δ 1d",
                    f"{latest['change_1d']:+.3f}" if latest["change_1d"] is not None else "—")
        c_7d.metric("Δ 7d",
                    f"{latest['change_7d']:+.3f}" if latest["change_7d"] is not None else "—")
        c_30d.metric("Δ 30d",
                     f"{latest['change_30d']:+.3f}" if latest["change_30d"] is not None else "—")
        with c_age:
            st.markdown("**Última coleta**")
            st.markdown(_age_badge(ts_coll), unsafe_allow_html=True)
            st.caption(f"ref: {latest['date'].strftime('%Y-%m-%d')}")

        # Chart 60d
        import yaml as _yaml
        _cfg = _yaml.safe_load((_REPO_ROOT / "config.yaml").read_text(encoding="utf-8"))
        _days = int(_cfg.get("truflation", {}).get("history_days", 60))

        df_plot = df.tail(_days).copy()
        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=df_plot["date"], y=df_plot["value"],
            mode="lines", name="TruCPI-US (YoY %)",
            line=dict(color="#2a9df4", width=2),
            fill="tozeroy", fillcolor="rgba(42,157,244,0.15)",
        ))
        fig.update_layout(
            height=360,
            margin=dict(l=10, r=10, t=30, b=10),
            hovermode="x unified",
            yaxis_title="YoY %",
            xaxis_title=None,
            showlegend=False,
            template="plotly_dark",
        )
        st.plotly_chart(fig, use_container_width=True)

        # Expander com dados brutos
        with st.expander("Dados brutos (últimos 30 dias)"):
            st.dataframe(
                df.tail(30)[["date", "value", "change_1d", "change_7d", "change_30d"]]
                    .sort_values("date", ascending=False),
                hide_index=True, use_container_width=True,
            )

        # Botao re-coletar manual
        with st.container():
            if st.button("🔄 Re-coletar agora", key="tru_rerun"):
                from collectors import truflation as _t
                with st.spinner("Atualizando Truflation..."):
                    _res = _t.collect()
                if _res.get("status") == "ok":
                    st.success(f"Atualizado — {_res['rows_upserted']} pontos.")
                    st.rerun()
                else:
                    st.error(f"Falha: {_res.get('error', 'erro desconhecido')}")


render_footer()
