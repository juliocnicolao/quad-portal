"""Thesis Monitor — radar de convergencia cross-ativo (estilo Unusual Whales).

Ferramenta de DESCOBERTA de oportunidades, nao de tracking de posicao.

Fluxo:
1. Usuario escolhe preset tematico (Default, Energy, Volatility, ...)
2. Ve tabela ranqueada da watchlist ordenada por convergencia (bear ou bull)
3. Ve flags de atividade anomala (vol spike, rompimento de canal, volume surge)
4. Clica numa linha da tabela para analise aprofundada do ticker escolhido

**Ativos suportados:** qualquer ticker com dados no yfinance. Ativos sem option
chain entram na tabela com N/A nas colunas de options; scorecard usa 2 pilares
(Tecnico + Momentum).

**Limitacoes:**
- IV Rank e proxy via HV 252d (nao IV historica real).
- Detector de unusual activity compara HV20 de hoje vs HV20 de 7 dias atras —
  aproximacao ate persistirmos snapshots de IV real.
- Custom watchlist vive apenas em st.session_state (sem persistencia de disco).
  TODO: migrar para query param no futuro.

Toda matematica pura esta em services/options_analytics.py; I/O de chain em
services/options_service.py; catalogo de presets em services/watchlist_presets.py.
"""

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

st.set_page_config(page_title="Thesis Monitor | QUAD", page_icon="🎯",
                   layout="wide", initial_sidebar_state="expanded")

from components.layout        import inject_css, render_sidebar, render_footer, page_header
from components.cards         import section_header, metric_card, error_card
from services                 import data_service       as data
from services                 import options_service    as opt_svc
from services                 import options_analytics  as oa
from services                 import iv_history_service as iv_hist
from services.watchlist_presets import (WATCHLIST_PRESETS, get_preset,
                                        get_preset_names)
from utils                    import (fmt_currency_usd, fmt_pct, CACHE_TTL,
                                      COLOR_RED, COLOR_GREEN)

inject_css()
render_sidebar()
page_header("Thesis Monitor — Radar de Convergencia",
            "Scanner cross-ativo por pilares tecnico/momentum/options · detector de atividade anomala")


# ── 1. Preset selector + watchlist ───────────────────────────────────────────
section_header("Watchlist", "Preset tematico ou customizado")

if "tm_preset" not in st.session_state:
    st.session_state["tm_preset"] = "Default"
if "tm_custom_watchlist" not in st.session_state:
    st.session_state["tm_custom_watchlist"] = ", ".join(get_preset("Default"))

wl_c1, wl_c2 = st.columns([1, 3])
with wl_c1:
    preset = st.selectbox("Preset:", options=get_preset_names(),
                          index=get_preset_names().index(st.session_state["tm_preset"]),
                          key="tm_preset_sel")
    if preset != st.session_state["tm_preset"]:
        st.session_state["tm_preset"] = preset
        if preset != "Custom":
            st.session_state["tm_custom_watchlist"] = ", ".join(get_preset(preset))
        st.rerun()

with wl_c2:
    if preset == "Custom":
        raw = st.text_area("Tickers customizados (separar por virgula):",
                           value=st.session_state["tm_custom_watchlist"],
                           height=70, key="tm_wl_raw")
        st.session_state["tm_custom_watchlist"] = raw
    else:
        st.text_input("Tickers do preset:",
                      value=", ".join(get_preset(preset)),
                      disabled=True, key="tm_wl_display")


def _parse_tickers(raw: str) -> list[str]:
    toks = [t.strip().upper() for t in raw.replace("\n", ",").replace(";", ",").split(",")]
    seen, out = set(), []
    for t in toks:
        if t and t not in seen:
            seen.add(t); out.append(t)
    return out


if preset == "Custom":
    tickers = _parse_tickers(st.session_state["tm_custom_watchlist"])
else:
    tickers = get_preset(preset)

if not tickers:
    st.info("Watchlist vazia. Escolha um preset ou digite tickers em Custom.")
    render_footer(); st.stop()

st.caption(f"📊 {len(tickers)} ativos: {' · '.join(tickers)}")
st.markdown("---")


# ── 2. Opportunity Scanner ───────────────────────────────────────────────────
section_header("Opportunity Scanner",
               "Ranking por convergencia de pilares · click na linha abre a analise focal")

sc_c1, sc_c2 = st.columns([1, 3])
with sc_c1:
    direction = st.radio("Direcao:", options=["🔴 Bearish", "🟢 Bullish"],
                         horizontal=True, index=0, key="tm_direction")
direction_key = "bearish" if direction == "🔴 Bearish" else "bullish"


@st.cache_data(ttl=CACHE_TTL, show_spinner=False)
def _ticker_snapshot(ticker: str) -> dict:
    """Computa o snapshot agregado de 1 ticker. Cacheado 15min.

    Chama data_service + options_service + options_analytics e retorna
    dicionario de colunas ja prontas para a tabela do scanner.
    """
    snap: dict = {"ticker": ticker, "error": None}

    q = data.quote(ticker)
    if q.get("error") or q.get("price") is None:
        snap["error"] = f"sem cotacao ({q.get('source','?')})"
        return snap

    price = float(q["price"])
    snap["price"]     = price
    snap["change_1d"] = q.get("change_pct")

    hist = data.history(ticker, period="1y")
    change_5d = None
    current_hv = hv_7d_ago = None
    channel_pos = 50.0
    channel_pos_raw = 50.0
    channel_valid = False
    cur_vol = vol_avg20 = None

    if not hist.empty and "Close" in hist.columns:
        closes = hist["Close"].dropna()
        if len(closes) > 5:
            change_5d = (closes.iloc[-1] / closes.iloc[-6] - 1) * 100
        hv_series = oa.calc_hv(closes, window=20).dropna()
        if not hv_series.empty:
            current_hv = float(hv_series.iloc[-1])
            if len(hv_series) > 7:
                hv_7d_ago = float(hv_series.iloc[-8])
        ch = oa.regression_channel(hist, n_std=2.0, current_spot=price)
        channel_pos     = ch["position_pct"]
        channel_pos_raw = ch["position_pct_raw"]
        channel_valid   = ch["is_valid"]
        if "Volume" in hist.columns:
            vols = hist["Volume"].dropna()
            if len(vols) > 20:
                cur_vol   = float(vols.iloc[-1])
                vol_avg20 = float(vols.tail(20).mean())

    # Variacao 20d para momentum
    change_20d = 0.0
    if not hist.empty and "Close" in hist.columns:
        closes = hist["Close"].dropna()
        if len(closes) > 20:
            change_20d = (closes.iloc[-1] / closes.iloc[-21] - 1) * 100

    chain = opt_svc.get_chain(ticker, max_expiries=4)
    has_chain = chain["available"] and not (chain["calls"].empty and chain["puts"].empty)
    pc_oi  = chain["pc_oi"] if has_chain else None
    gex_sum = None
    iv_atm = None
    if has_chain:
        g = oa.calc_gex(chain, spot=price)
        if not g.empty:
            gex_sum = float(g["gex_total"].sum())
        iv_atm = iv_hist.compute_atm_iv(chain, spot=price)

    # IV Rank real (CBOE proxy ou self-history)
    iv_rank_info = iv_hist.get_iv_rank(ticker, current_iv=iv_atm)

    # IV/HV spread — sinal de vol regime (IV > HV = opcoes caras)
    iv_hv_ratio = None
    if iv_atm is not None and current_hv is not None and current_hv > 0:
        iv_hv_ratio = iv_atm / current_hv

    # Pilares — so adiciona os disponiveis
    tech_bias = oa.classify_technical(channel_pos) if channel_valid else None
    mom_bias  = oa.classify_momentum(change_20d)
    of_bias   = oa.classify_options_flow(pc_oi) if pc_oi is not None else None
    pillars = [
        {"name": "Tecnico",      "bias": tech_bias},
        {"name": "Momentum",     "bias": mom_bias},
        {"name": "Options Flow", "bias": of_bias},
    ]
    pillars = [p for p in pillars if p["bias"] is not None]

    snap.update({
        "change_5d":        change_5d,
        "change_20d":       change_20d,
        "channel_pos":      channel_pos,
        "channel_pos_raw":  channel_pos_raw,
        "channel_valid":    channel_valid,
        "current_hv":       current_hv,
        "hv_7d_ago":        hv_7d_ago,
        "iv_atm":           iv_atm,
        "iv_rank":          iv_rank_info["rank"],       # float | None
        "iv_rank_source":   iv_rank_info["source"],
        "iv_rank_n_days":   iv_rank_info["n_days"],
        "iv_rank_index":    iv_rank_info["vol_index"],
        "iv_hv_ratio":      iv_hv_ratio,
        "pc_oi":            pc_oi,
        "gex_total":        gex_sum,
        "has_chain":        has_chain,
        "pillars":          pillars,
        "current_volume":   cur_vol,
        "avg_volume_20d":   vol_avg20,
    })
    return snap


# Coleta snapshots (cacheado)
progress = st.progress(0.0, text="Carregando watchlist...")
snapshots: list[dict] = []
for i, t in enumerate(tickers):
    snapshots.append(_ticker_snapshot(t))
    progress.progress((i + 1) / len(tickers), text=f"Carregando {t}...")
progress.empty()

# Helpers de display pra IV Rank
def _iv_rank_display(s: dict) -> tuple[float | None, str]:
    """Retorna (valor_progressbar, legenda) para a coluna IV Rank.

    valor_progressbar e None quando nao temos rank (ex: construindo historico) —
    ProgressColumn renderiza vazio. A legenda vai numa coluna textual ao lado.
    """
    src = s.get("iv_rank_source")
    rank = s.get("iv_rank")
    n = s.get("iv_rank_n_days") or 0
    iv = s.get("iv_atm")
    iv_s = f"{iv*100:.0f}%" if iv else "—"
    if src == "cboe":
        idx = s.get("iv_rank_index") or "?"
        return rank, f"{int(rank)} · {idx} · IV {iv_s}"
    if src == "self_history":
        return rank, f"{int(rank)} · N={n}d · IV {iv_s}"
    if src == "insufficient":
        return None, f"⏳ {n}/20d · IV {iv_s}"
    # no_chain
    return None, "—"


# Monta dataframe
rows: list[dict] = []
for s in snapshots:
    if s.get("error"):
        rows.append({
            "Ticker": s["ticker"], "Preco": None, "Var 1d": None, "Var 5d": None,
            "Canal %": None, "P/C OI": None, "IV Rank": None, "IV Info": "—",
            "IV/HV": None, "GEX (M)": None,
            "Score": -999, "Veredito": f"⚠ {s['error']}",
        })
        continue
    conv = oa.calculate_convergence_score(s["pillars"], direction=direction_key)
    ivr_val, ivr_lbl = _iv_rank_display(s)
    rows.append({
        "Ticker":    s["ticker"],
        "Preco":     s["price"],
        "Var 1d":    s.get("change_1d"),
        "Var 5d":    s.get("change_5d"),
        "Canal %":   s["channel_pos"] if s["channel_valid"] else None,
        "P/C OI":    s.get("pc_oi"),
        "IV Rank":   ivr_val,
        "IV Info":   ivr_lbl,
        "IV/HV":     s.get("iv_hv_ratio"),
        "GEX (M)":   (s["gex_total"] / 1_000_000) if s.get("gex_total") is not None else None,
        "Score":     conv["score"],
        "Veredito":  f"{conv['emoji']} {conv['label']}  ({conv['bear_count']}B/{conv['bull_count']}L de {conv['total']})",
    })

scanner_df = pd.DataFrame(rows).sort_values("Score", ascending=False).reset_index(drop=True)

# Render com selecao nativa
try:
    event = st.dataframe(
        scanner_df,
        on_select="rerun",
        selection_mode="single-row",
        hide_index=True,
        use_container_width=True,
        column_config={
            "Ticker":   st.column_config.TextColumn("Ticker", width="small"),
            "Preco":    st.column_config.NumberColumn("Preco", format="$%.2f"),
            "Var 1d":   st.column_config.NumberColumn("Var 1d", format="%.2f%%"),
            "Var 5d":   st.column_config.NumberColumn("Var 5d", format="%.2f%%"),
            "Canal %":  st.column_config.ProgressColumn("Canal %",
                            help="Posicao no canal de regressao (0=piso, 100=topo)",
                            format="%.0f%%", min_value=0, max_value=100),
            "P/C OI":   st.column_config.NumberColumn("P/C OI", format="%.2f"),
            "IV Rank":  st.column_config.ProgressColumn("IV Rank",
                            help="Percentil do IV atual vs historico (CBOE vol index "
                                 "quando disponivel; senao self-history diaria).",
                            format="%.0f", min_value=0, max_value=100),
            "IV Info":  st.column_config.TextColumn("fonte",
                            help="Fonte do IV Rank. 'CBOE' = indice oficial. "
                                 "'N=Xd' = snapshots proprios acumulados. "
                                 "'⏳ N/20d' = construindo historico."),
            "IV/HV":    st.column_config.NumberColumn("IV/HV",
                            help=">1.2 = opcoes caras vs realizado (vender); "
                                 "<0.8 = opcoes baratas (comprar).",
                            format="%.2f"),
            "GEX (M)":  st.column_config.NumberColumn("GEX (M)",
                            help="Gamma Exposure total em milhoes USD",
                            format="%.2f"),
            "Score":    st.column_config.NumberColumn("Conv",
                            help="Convergence score: pilares_favor - pilares_contra",
                            format="%d"),
            "Veredito": st.column_config.TextColumn("Veredito", width="medium"),
        },
        key="tm_scanner_df",
    )
    # API de selecao mudou entre versoes — tenta ambos os shapes
    selected_rows = []
    try:
        sel = getattr(event, "selection", None) or event.get("selection", {})
        selected_rows = getattr(sel, "rows", None) or sel.get("rows", [])
    except Exception:
        selected_rows = []
    table_api_ok = True
except Exception as _e:
    # Fallback para Streamlit antigo que nao suporta on_select
    st.dataframe(scanner_df, hide_index=True, use_container_width=True)
    selected_rows = []
    table_api_ok = False
    st.caption(f"⚠ API de selecao de linhas indisponivel ({_e}). Use o seletor abaixo.")

# Seletor fallback (sempre visivel como backup)
fallback_default = int(selected_rows[0]) if selected_rows else 0
fallback_default = max(0, min(fallback_default, len(scanner_df) - 1))
focal = st.selectbox(
    "Ou selecione ticker para analise focal:",
    options=list(scanner_df["Ticker"]),
    index=fallback_default,
    key="tm_focal_sel",
)
# Se usuario clicou na linha, usa a linha clicada
if selected_rows:
    focal = scanner_df.iloc[int(selected_rows[0])]["Ticker"]

st.markdown("---")


# ── 3. Unusual Activity ──────────────────────────────────────────────────────
section_header("Unusual Activity",
               "Flags automaticas de mudancas de regime · HV proxy (7d)")

snap_by_ticker = {s["ticker"]: s for s in snapshots}
flag_rows: list[dict] = []
for t in tickers:
    s = snap_by_ticker.get(t)
    if not s or s.get("error"):
        continue
    flags = oa.detect_unusual_activity({
        "current_hv":       s.get("current_hv"),
        "hv_7d_ago":        s.get("hv_7d_ago"),
        "channel_pos_raw":  s.get("channel_pos_raw"),
        "pc_oi":            s.get("pc_oi"),
        "pc_oi_7d_ago":     None,  # ainda sem persistencia de snapshot de chain
        "current_volume":   s.get("current_volume"),
        "avg_volume_20d":   s.get("avg_volume_20d"),
    })
    for f in flags:
        flag_rows.append({"ticker": t, **f})

if not flag_rows:
    st.caption("✓ Nenhuma atividade anomala detectada na watchlist atual.")
else:
    _sev_color = {
        "bearish":  COLOR_RED,
        "bullish":  COLOR_GREEN,
        "neutral":  "#d4a017",  # amarelo/ambar para mudancas de vol
    }
    # Render em grid de 3 colunas
    flags_cols = st.columns(3)
    for i, f in enumerate(flag_rows):
        col = _sev_color[f["severity"]]
        mag = f["magnitude"]
        if f["type"] == "volume_surge":
            mag_str = f"{mag:.1f}x media"
        elif f["type"] in ("vol_spike", "vol_crush"):
            mag_str = f"{mag:+.1f} p.p. HV"
        elif f["type"].startswith("channel"):
            mag_str = f"{mag:+.1f} pts fora"
        elif f["type"].startswith("pc_shift"):
            mag_str = f"Δ {mag:+.2f}"
        else:
            mag_str = f"{mag:.2f}"
        with flags_cols[i % 3]:
            st.markdown(
                f'<div style="background:#1A1A1A;border-left:3px solid {col};'
                f'border-radius:6px;padding:0.7rem 0.9rem;margin-bottom:0.6rem;">'
                f'<div style="font-size:0.7rem;color:#888;text-transform:uppercase;'
                f'letter-spacing:0.08em;">{f["ticker"]}</div>'
                f'<div style="font-size:0.92rem;color:#F0F0F0;font-weight:600;'
                f'margin:0.15rem 0 0.15rem 0;">{f["label"]}</div>'
                f'<div style="font-size:0.72rem;color:{col};font-weight:600;">'
                f'{mag_str}</div></div>',
                unsafe_allow_html=True,
            )

st.markdown("---")


# ── 4. Analise focal do ticker selecionado ──────────────────────────────────
section_header(f"Analise focal — {focal}",
               "Candlestick + canal de regressao · Options flow · Scorecard detalhado")

focal_snap = snap_by_ticker.get(focal)
if not focal_snap or focal_snap.get("error"):
    st.warning(f"Sem dados para {focal}. {focal_snap.get('error','') if focal_snap else ''}")
    render_footer(); st.stop()

with st.spinner(f"Carregando grafico de {focal}..."):
    hist = data.history(focal, period="1y")

spot = focal_snap["price"]

if hist.empty or "Close" not in hist.columns:
    st.warning(f"Historico de {focal} indisponivel.")
else:
    channel = oa.regression_channel(hist, n_std=2.0, current_spot=spot)
    fig = go.Figure()
    fig.add_trace(go.Candlestick(
        x=hist.index, open=hist["Open"], high=hist["High"],
        low=hist["Low"], close=hist["Close"], name=focal,
        increasing_line_color=COLOR_GREEN, decreasing_line_color=COLOR_RED,
    ))
    if channel["is_valid"]:
        x_axis = hist.index[-len(channel["mean"]):]
        fig.add_trace(go.Scatter(x=x_axis, y=channel["upper"], mode="lines",
                                 line=dict(color="#888", width=1, dash="dot"),
                                 name="+2σ"))
        fig.add_trace(go.Scatter(x=x_axis, y=channel["mean"], mode="lines",
                                 line=dict(color="#aaa", width=1),
                                 name="Regressao"))
        fig.add_trace(go.Scatter(x=x_axis, y=channel["lower"], mode="lines",
                                 line=dict(color="#888", width=1, dash="dot"),
                                 name="-2σ"))
    fig.update_layout(
        template="plotly_dark", height=430, margin=dict(l=10, r=10, t=30, b=10),
        paper_bgcolor="#0D0D0D", plot_bgcolor="#0D0D0D",
        xaxis_rangeslider_visible=False, showlegend=True,
        legend=dict(orientation="h", y=1.02, x=0),
    )
    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
    if not channel["is_valid"]:
        st.info(channel["reason"])

# Metricas focais — linha 1: preco/canal/momentum
m1, m2, m3 = st.columns(3)
with m1: metric_card("Preco", fmt_currency_usd(spot), focal_snap.get("change_1d"))
with m2:
    cp = focal_snap["channel_pos"]
    hint = ""
    if focal_snap["channel_valid"]:
        if cp > 85: hint = "⚠ topo do canal"
        elif cp < 15: hint = "⚠ piso do canal"
    metric_card("Posicao no canal",
                f"{cp:.0f}%" if focal_snap["channel_valid"] else "n/d", hint=hint)
with m3:
    metric_card("Variacao 20d", f"{focal_snap['change_20d']:+.1f}%")

# Metricas focais — linha 2: trindade de volatilidade (IV Rank + IV atual + IV/HV)
v1, v2, v3, v4 = st.columns(4)
with v1:
    rank = focal_snap.get("iv_rank")
    src  = focal_snap.get("iv_rank_source")
    nd   = focal_snap.get("iv_rank_n_days") or 0
    if rank is not None:
        hint = ""
        if rank >= 70:   hint = "⚠ IV caro · considerar VENDER premio"
        elif rank <= 30: hint = "⚠ IV barato · considerar COMPRAR premio"
        source_tag = {"cboe": f"CBOE {focal_snap.get('iv_rank_index','')}",
                      "self_history": f"self N={nd}d"}.get(src, src)
        metric_card("IV Rank", f"{rank:.0f}", hint=f"{hint}  ·  {source_tag}".strip(" ·"))
    else:
        metric_card("IV Rank", "—",
                    hint=f"⏳ construindo ({nd}/20d)" if src == "insufficient"
                         else "sem chain")
with v2:
    iv = focal_snap.get("iv_atm")
    metric_card("IV ATM (atual)", f"{iv*100:.1f}%" if iv else "n/d")
with v3:
    hv = focal_snap.get("current_hv")
    metric_card("HV 20d", f"{hv*100:.1f}%" if hv else "n/d")
with v4:
    ratio = focal_snap.get("iv_hv_ratio")
    if ratio is not None:
        hint = ""
        if ratio > 1.2:   hint = "opcoes caras vs realizado"
        elif ratio < 0.8: hint = "opcoes baratas vs realizado"
        else:             hint = "alinhado ao realizado"
        metric_card("IV/HV", f"{ratio:.2f}", hint=hint)
    else:
        metric_card("IV/HV", "n/d")

# Options flow focal
chain = opt_svc.get_chain(focal, max_expiries=6)
has_chain = chain["available"] and not (chain["calls"].empty and chain["puts"].empty)

if has_chain:
    st.markdown("")
    o1, o2, o3, o4 = st.columns(4)
    with o1:
        pc = chain["pc_oi"]
        metric_card("P/C ratio (OI)", f"{pc:.2f}",
                    hint="bearish" if pc > 1.1 else ("bullish" if pc < 0.7 else "neutro"))
    with o2:
        metric_card("P/C ratio (Volume)", f"{chain['pc_vol']:.2f}")
    with o3:
        metric_card("IV medio calls", f"{chain['iv_avg_calls']*100:.1f}%")
    with o4:
        metric_card("IV medio puts",  f"{chain['iv_avg_puts']*100:.1f}%")

    gex_df = oa.calc_gex(chain, spot=spot)
    if not gex_df.empty:
        lo, hi = spot * 0.5, spot * 1.5
        g = gex_df[(gex_df["strike"] >= lo) & (gex_df["strike"] <= hi)].copy()
        if not g.empty:
            g["color"] = np.where(g["gex_total"] >= 0, COLOR_GREEN, COLOR_RED)
            fig_gex = go.Figure()
            fig_gex.add_trace(go.Bar(x=g["strike"], y=g["gex_total"],
                                     marker_color=g["color"], name="GEX total"))
            fig_gex.add_vline(x=spot, line_color="#F0F0F0", line_dash="dash",
                              annotation_text=f"spot ${spot:.2f}",
                              annotation_position="top")
            fig_gex.update_layout(
                template="plotly_dark", height=320,
                margin=dict(l=10, r=10, t=30, b=10),
                paper_bgcolor="#0D0D0D", plot_bgcolor="#0D0D0D",
                title="GEX por strike (±50% do spot)",
                xaxis_title="Strike", yaxis_title="Gamma Exposure (USD)",
                showlegend=False,
            )
            st.plotly_chart(fig_gex, use_container_width=True,
                            config={"displayModeBar": False})
            gex_total = float(g["gex_total"].sum())
            if gex_total >= 0:
                st.caption("**GEX total positivo** — dealers tendem a estabilizar o preco.")
            else:
                st.caption("**GEX total negativo** — dealers tendem a amplificar movimentos.")
else:
    st.info(f"Options chain nao disponivel para {focal}. "
            "Scorecard usa apenas Tecnico + Momentum.")

# Scorecard detalhado do focal
pillars = focal_snap["pillars"]
iv_label = oa.classify_iv_rank(focal_snap["iv_rank"])

_chip_col = {"BEARISH": COLOR_RED, "BULLISH": COLOR_GREEN, "NEUTRAL": "#888"}
chip_html = ""
for p in pillars:
    c = _chip_col.get(p["bias"], "#555")
    chip_html += (f'<span style="display:inline-block;background:{c};color:#fff;'
                  f'font-size:0.72rem;font-weight:700;padding:4px 10px;'
                  f'border-radius:4px;margin-right:6px;letter-spacing:0.05em;">'
                  f'{p["name"]}: {p["bias"]}</span>')
_iv_col = {"HIGH": COLOR_RED, "LOW": COLOR_GREEN, "MID": "#888", "N/A": "#555"}.get(iv_label, "#555")
chip_html += (f'<span style="display:inline-block;background:{_iv_col};color:#fff;'
              f'font-size:0.72rem;font-weight:700;padding:4px 10px;border-radius:4px;'
              f'letter-spacing:0.05em;">IV Rank: {iv_label}</span>')
st.markdown(f'<div style="margin:0.6rem 0 0.2rem 0;">{chip_html}</div>',
            unsafe_allow_html=True)

conv = oa.calculate_convergence_score(pillars, direction=direction_key)
if conv["verdict"] == "STRONG_BEAR":
    st.markdown(
        f'<div style="background:#2a1818;border-left:4px solid {COLOR_RED};'
        f'padding:0.9rem 1rem;border-radius:4px;margin-top:0.5rem;">'
        f'<b style="color:{COLOR_RED};">{conv["emoji"]} {conv["label"]}</b> — '
        f'{conv["bear_count"]}/{conv["total"]} pilares bearish.</div>',
        unsafe_allow_html=True)
elif conv["verdict"] == "STRONG_BULL":
    st.markdown(
        f'<div style="background:#182a18;border-left:4px solid {COLOR_GREEN};'
        f'padding:0.9rem 1rem;border-radius:4px;margin-top:0.5rem;">'
        f'<b style="color:{COLOR_GREEN};">{conv["emoji"]} {conv["label"]}</b> — '
        f'{conv["bull_count"]}/{conv["total"]} pilares bullish.</div>',
        unsafe_allow_html=True)
else:
    st.caption(f"{conv['emoji']} {conv['label']} — "
               f"{conv['bear_count']}B / {conv['bull_count']}L de {conv['total']} pilares.")


render_footer()
