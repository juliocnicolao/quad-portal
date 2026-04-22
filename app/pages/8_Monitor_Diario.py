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
            "SELECT id, ts_started, ts_finished, status, sections, notes "
            "FROM scheduler_runs ORDER BY id DESC LIMIT 1"
        ).fetchone()
    if not row:
        return None
    out = dict(row)
    try:
        out["sections"] = json.loads(out["sections"] or "{}")
    except json.JSONDecodeError:
        out["sections"] = {}
    try:
        out["notes"] = json.loads(out["notes"]) if out.get("notes") else {}
    except json.JSONDecodeError:
        out["notes"] = {}
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
    # Async: dispara o runner em subprocess pra não travar a UI.
    # Status fica visível via badges + expander de freshness que
    # atualizam no próximo rerun.
    def _spawn_runner_bg() -> int:
        import subprocess, sys as _sys
        # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP no Windows → UI não espera.
        creationflags = 0
        if _sys.platform == "win32":
            creationflags = 0x00000008 | 0x00000200  # DETACHED | NEW_GROUP
        log_path = _REPO_ROOT / "logs" / "scheduler_run.log"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        # redireciona stdout/stderr pro mesmo log do scheduler
        fh = open(log_path, "ab")
        p = subprocess.Popen(
            [_sys.executable, "-m", "scheduler.runner"],
            cwd=str(_REPO_ROOT),
            stdout=fh, stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            close_fds=True,
            creationflags=creationflags,
        )
        return p.pid

    if st.button("▶ Rodar agora", key="hdr_run_now",
                 help="Dispara scheduler runner em background (UI não trava)"):
        try:
            pid = _spawn_runner_bg()
            st.toast(f"Runner disparado (PID {pid}). Acompanhe pelos badges.",
                     icon="🚀")
            st.session_state["_uw_last_spawn_ts"] = datetime.now(timezone.utc).isoformat()
        except Exception as _ex:
            st.error(f"Falha ao disparar runner: {_ex}")

# Freshness por seção: idade do último ts_collected de cada tabela
with get_conn() as _conn:
    _fresh = {
        "calendar":   _conn.execute(
            "SELECT MAX(ts_collected) FROM economic_events"
        ).fetchone()[0],
        "uw":         _conn.execute(
            "SELECT MAX(ts_collected) FROM options_flow_daily"
        ).fetchone()[0],
        "truflation": _conn.execute(
            "SELECT MAX(ts_collected) FROM truflation_history"
        ).fetchone()[0],
    }
f_items = []
for key, label in [("calendar", "📅 Calendário"),
                   ("uw",        "📊 Options"),
                   ("truflation","🌡️ Truflation")]:
    f_items.append(f"{label}: {_age_badge(_fresh.get(key))}")
st.markdown("<div style='font-size:0.8rem;'>"
            + " &nbsp;·&nbsp; ".join(f_items)
            + "</div>", unsafe_allow_html=True)

# Erros detalhados do ultimo run (collapsed por padrao)
if last and last.get("notes"):
    _notes = last["notes"]
    total_fails = sum(len(v.get("failed", []))
                      for v in _notes.values() if isinstance(v, dict))
    if total_fails:
        with st.expander(f"⚠️ {total_fails} falha(s) no último run · detalhes",
                         expanded=False):
            for sec, payload in _notes.items():
                if not isinstance(payload, dict):
                    continue
                fails = payload.get("failed") or []
                err   = payload.get("error")
                if err and not fails:
                    st.error(f"**{sec}** · {err}")
                for f in fails:
                    if sec == "calendar":
                        st.caption(
                            f"📅 **{f.get('country','?')}** · "
                            f"{f.get('name','?')} (slug: `{f.get('slug','?')}`)"
                            f"  \n&nbsp;&nbsp;↳ `{f.get('error','')}`"
                        )
                    elif sec == "uw":
                        st.caption(
                            f"📊 **{f.get('ticker','?')}** "
                            f"({f.get('stage','?')})"
                            f"  \n&nbsp;&nbsp;↳ `{f.get('error','')}`"
                        )
                    else:
                        st.caption(f"**{sec}** · {f}")

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
            # v pode chegar como float OU string formatada ("+0.05", "—").
            if v is None or (isinstance(v, float) and pd.isna(v)) or v == "—":
                return ""
            try:
                n = float(v) if not isinstance(v, (int, float)) else v
            except (TypeError, ValueError):
                return ""
            if n > 0.05:  return "color: #0a9; font-weight: 600;"
            if n < -0.05: return "color: #c33; font-weight: 600;"
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
    st.caption("PBR · TLT · SPY · EWZ — daily stats (volume, OI, IV rank, "
               "net premium) + aggregate GEX 1Y. Fonte: unusualwhales.com "
               "sem login (API pública do frontend). "
               "⚠ O endpoint `/market_state_all` retorna apenas os últimos "
               "5 dias por call — a série histórica cresce a cada run 2×/dia "
               "e vira útil estatisticamente após ~30 dias de acúmulo no DB.")

    import pandas as pd
    import plotly.graph_objects as go

    with get_conn() as _conn:
        _flow_rows = _conn.execute(
            "SELECT ticker, date, close, pct_change, pc_ratio, volume, "
            "       c_vol, p_vol, vol_30d_ratio, total_oi, ivr, net_prem, "
            "       total_prem, ts_collected "
            "FROM options_flow_daily ORDER BY date DESC, ticker ASC"
        ).fetchall()
        _gex_rows = _conn.execute(
            "SELECT ticker, date, close, call_gex, put_gex, call_delta, put_delta "
            "FROM gex_daily ORDER BY date ASC, ticker ASC"
        ).fetchall()

    if not _flow_rows and not _gex_rows:
        st.warning("Ainda não há dados de Unusual Whales no banco.")
        if st.button("🔄 Coletar agora", key="uw_first_run"):
            from collectors import unusual_whales as _uw
            with st.spinner("Coletando options flow + GEX (4 tickers)..."):
                _res = _uw.collect()
            status = _res.get("status")
            if status == "ok":
                st.success(
                    f"OK — {_res['flow_upserted']} linhas de flow e "
                    f"{_res['gex_upserted']} linhas de GEX."
                )
                st.rerun()
            else:
                st.error(f"Falha ({status}): {_res.get('failed') or _res.get('error')}")
    else:
        df_flow = pd.DataFrame([dict(r) for r in _flow_rows])
        df_gex  = pd.DataFrame([dict(r) for r in _gex_rows])

        # Cards por ticker (último dia disponível por ticker)
        latest_per_ticker = (df_flow.sort_values(["ticker", "date"])
                                   .groupby("ticker").tail(1)
                                   .set_index("ticker"))

        ts_coll = df_flow["ts_collected"].max()
        st.markdown(
            f"**Última coleta:** {_age_badge(ts_coll)}",
            unsafe_allow_html=True,
        )

        # Cards em linhas de até 4 tickers (evita colunas apertadas se >4).
        _per_row = 4
        _items = list(latest_per_ticker.iterrows())
        for _start in range(0, len(_items), _per_row):
            _chunk = _items[_start:_start + _per_row]
            _cols = st.columns(len(_chunk))
            for col, (tk, row) in zip(_cols, _chunk):
                with col:
                    st.markdown(f"#### {tk}")
                    close = row.get("close")
                    pct = row.get("pct_change")
                    st.metric(
                        "Close",
                        f"{close:.2f}" if close is not None else "—",
                        delta=(f"{pct*100:+.2f}%" if pct is not None else None),
                    )
                    ivr = row.get("ivr")
                    st.caption(f"IV Rank: **{ivr:.1f}**" if ivr is not None else "IV Rank: —")
                    pcr = row.get("pc_ratio")
                    st.caption(f"P/C Vol: **{pcr:.2f}**" if pcr is not None else "P/C Vol: —")
                    np_ = row.get("net_prem")
                    if np_ is not None:
                        sign = "🟢" if np_ > 0 else "🔴"
                        st.caption(f"Net prem: {sign} **${np_/1e6:+.2f}M**")

        st.markdown("---")

        # Tabela completa — últimos registros de cada ticker
        st.markdown("**Histórico diário (SQLite vai acumulando a cada run)**")
        show = df_flow[["date", "ticker", "close", "pct_change", "pc_ratio",
                         "volume", "ivr", "net_prem", "total_prem"]].copy()
        show["pct_change"] = (show["pct_change"] * 100).round(2)
        show["pc_ratio"]   = show["pc_ratio"].round(2)
        show["ivr"]        = show["ivr"].round(1)
        show["net_prem"]   = (show["net_prem"] / 1e6).round(2)
        show["total_prem"] = (show["total_prem"] / 1e6).round(2)
        show = show.rename(columns={
            "pct_change": "%Δ", "pc_ratio": "P/C",
            "ivr": "IVR", "net_prem": "NetPrem ($M)",
            "total_prem": "TotPrem ($M)",
        })
        st.dataframe(show, use_container_width=True, hide_index=True)

        # GEX chart — call_gex vs put_gex por ticker (últimos 120 dias)
        if not df_gex.empty:
            st.markdown("**GEX diário agregado (últimos 120 dias)**")
            tickers_avail = sorted(df_gex["ticker"].unique())
            sel_tk = st.selectbox("Ticker", tickers_avail, key="uw_gex_ticker")
            sub = (df_gex[df_gex["ticker"] == sel_tk]
                   .sort_values("date").tail(120))
            sub["date"] = pd.to_datetime(sub["date"])
            fig = go.Figure()
            fig.add_trace(go.Bar(x=sub["date"], y=sub["call_gex"],
                                  name="Call GEX", marker_color="#2ca02c"))
            fig.add_trace(go.Bar(x=sub["date"], y=sub["put_gex"],
                                  name="Put GEX",  marker_color="#d62728"))
            fig.add_trace(go.Scatter(x=sub["date"], y=sub["close"],
                                      name="Close", yaxis="y2",
                                      line=dict(color="#1f77b4", width=2)))
            fig.update_layout(
                barmode="relative", height=380,
                margin=dict(t=20, b=40, l=20, r=20),
                yaxis=dict(title="GEX"),
                yaxis2=dict(title="Close", overlaying="y", side="right"),
                legend=dict(orientation="h", y=1.08),
            )
            st.plotly_chart(fig, use_container_width=True)

        if st.button("🔄 Re-coletar agora", key="uw_rerun"):
            from collectors import unusual_whales as _uw
            with st.spinner("Coletando..."):
                _res = _uw.collect()
            if _res.get("status") in ("ok", "partial"):
                st.success(
                    f"{_res['status']} — flow {_res['flow_upserted']}, "
                    f"gex {_res['gex_upserted']}"
                )
                st.rerun()
            else:
                st.error(f"Falha: {_res.get('failed') or _res.get('error')}")

with tab_tru:
    st.subheader("Truflation US CPI Inflation Index")

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
        df = df.sort_values("date").reset_index(drop=True)

        latest = df.iloc[-1]
        ts_coll = latest["ts_collected"]
        cur_val = float(latest["value"])

        # Header minimalista: valor atual + badge de coleta
        c_val, _pad, c_age = st.columns([2, 3, 2])
        c_val.metric("Valor atual (YoY %)", f"{cur_val:.2f}%")
        with c_age:
            st.markdown("**Última coleta**")
            st.markdown(_age_badge(ts_coll), unsafe_allow_html=True)
            st.caption(f"ref: {latest['date'].strftime('%Y-%m-%d')}")

        # Chart: janela completa disponivel (1Y)
        df_plot = df.copy()
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
        with st.expander("Dados brutos (últimos 60 dias)"):
            st.dataframe(
                df.tail(60)[["date", "value", "change_1d", "change_7d", "change_30d"]]
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
