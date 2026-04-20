"""Thesis Monitor — canal de regressao, options flow, P&L simulator, scorecard.

Pagina para monitoramento de teses direcionais estruturadas. Combina analise
tecnica (canal de regressao), fluxo de opcoes (P/C ratio, IV rank, GEX) e
simulacao de P&L em multiplos cenarios. Scorecard agrega 3-4 pilares em
veredito de convergencia.

**Ativos suportados:** qualquer ticker com dados no yfinance. Secoes de options
flow aparecem apenas para ativos com option chain (PBR, EWZ, SPY, XLE, etc).
Ativos sem chain (ex. BZ=F, BRL=X) mostram apenas analise tecnica + scorecard
com 2 pilares.

**Limitacoes conhecidas:**
- Dados fim-de-dia (yfinance). Para intraday, usar a plataforma do broker.
- IV Rank e proxy via HV252d, nao IV historica real.
- GEX assume convencao padrao de posicionamento dealer (short calls / long
  puts), pode divergir em eventos extremos.

Toda matematica pura esta em services/options_analytics.py; I/O em
services/options_service.py. Esta pagina apenas renderiza.
"""

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

st.set_page_config(page_title="Thesis Monitor | QUAD", page_icon="🎯",
                   layout="wide", initial_sidebar_state="expanded")

from components.layout import inject_css, render_sidebar, render_footer, page_header
from components.cards  import section_header, metric_card, error_card
from services           import data_service as data
from services           import options_service  as opt_svc
from services           import options_analytics as oa
from utils              import (fmt_currency_usd, fmt_pct, CACHE_TTL,
                                COLOR_RED, COLOR_GREEN)

inject_css()
render_sidebar()
page_header("Thesis Monitor",
            "Canal de regressao · Options flow · Simulador de P&L · Scorecard de convergencia")


# ── Config ───────────────────────────────────────────────────────────────────
DEFAULT_WATCHLIST = "PBR, EWZ, SPY, XLE, USO, VALE, BZ=F, BRL=X, ^VIX"


def _parse_tickers(raw: str) -> list[str]:
    toks = [t.strip().upper() for t in raw.replace("\n", ",").replace(";", ",").split(",")]
    seen, out = set(), []
    for t in toks:
        if t and t not in seen:
            seen.add(t); out.append(t)
    return out


# ── 1. Watchlist multi-ativo ─────────────────────────────────────────────────
section_header("Watchlist", "Ativos monitorados · preco, variacao diaria, 20 dias")

wl_key = "thesis_watchlist"
if wl_key not in st.session_state:
    st.session_state[wl_key] = DEFAULT_WATCHLIST

raw = st.text_area("Tickers (separados por virgula):",
                   value=st.session_state[wl_key], height=70, key="thesis_wl_input")
if raw != st.session_state[wl_key]:
    st.session_state[wl_key] = raw

tickers = _parse_tickers(st.session_state[wl_key])

with st.spinner("Atualizando cotacoes..."):
    wl_quotes = {t: data.quote(t) for t in tickers}
    wl_hist   = {t: data.history(t, period="3mo") for t in tickers}

cols = st.columns(min(len(tickers), 5) or 1)
for i, t in enumerate(tickers):
    q = wl_quotes[t]; h = wl_hist[t]
    with cols[i % len(cols)]:
        if q.get("error") or q.get("price") is None:
            error_card(t, tried=[q.get("source", "?")])
            continue
        price = q["price"]
        change_1d = q.get("change_pct")
        # variacao 20d
        change_20d = None
        if not h.empty and "Close" in h.columns:
            closes = h["Close"].dropna()
            if len(closes) > 20:
                change_20d = (closes.iloc[-1] / closes.iloc[-21] - 1) * 100
        hint = f"{t} · 20d: {change_20d:+.1f}%" if change_20d is not None else t
        metric_card(t, fmt_currency_usd(price), change_1d, hint=hint)

st.markdown("---")


# ── 2. Ativo focal ───────────────────────────────────────────────────────────
section_header("Analise focal", "Candlestick com canal de regressao +/- 2 sigma")

fc1, fc2, fc3 = st.columns([2, 1, 1])
with fc1:
    focal = st.selectbox("Ticker focal:", options=tickers,
                         index=0 if tickers else None,
                         key="thesis_focal")
with fc2:
    period = st.selectbox("Periodo:", ["3mo", "6mo", "1y", "2y"], index=2)
with fc3:
    n_std = st.select_slider("Canal (sigmas):", options=[1.0, 1.5, 2.0, 2.5, 3.0], value=2.0)

if not focal:
    st.info("Adicione ao menos um ticker na watchlist para analisar.")
    render_footer(); st.stop()

with st.spinner(f"Carregando {focal}..."):
    hist = data.history(focal, period=period)
    focal_q = data.quote(focal)

spot = focal_q.get("price")
if hist.empty or "Close" not in hist.columns or spot is None:
    st.warning(f"Historico de {focal} indisponivel. Fontes testadas: "
               f"{focal_q.get('source', '?')} · {hist.attrs.get('source', '?')}")
    render_footer(); st.stop()

# Canal + metricas
channel = oa.regression_channel(hist, n_std=n_std, current_spot=spot)
closes  = hist["Close"].dropna()
hv20    = oa.calc_hv(closes, window=20).iloc[-1] if len(closes) > 20 else float("nan")
iv_rank = oa.calc_iv_rank(closes)
change_20d = (closes.iloc[-1] / closes.iloc[-21] - 1) * 100 if len(closes) > 20 else 0.0

# Candlestick + canal
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
                             name=f"+{n_std}σ"))
    fig.add_trace(go.Scatter(x=x_axis, y=channel["mean"], mode="lines",
                             line=dict(color="#aaa", width=1),
                             name="Regressao"))
    fig.add_trace(go.Scatter(x=x_axis, y=channel["lower"], mode="lines",
                             line=dict(color="#888", width=1, dash="dot"),
                             name=f"-{n_std}σ"))
fig.update_layout(
    template="plotly_dark", height=460, margin=dict(l=10, r=10, t=30, b=10),
    paper_bgcolor="#0D0D0D", plot_bgcolor="#0D0D0D",
    xaxis_rangeslider_visible=False, showlegend=True,
    legend=dict(orientation="h", y=1.02, x=0),
)
st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})

if not channel["is_valid"]:
    st.info(channel["reason"])

# Metricas focais
m1, m2, m3, m4, m5 = st.columns(5)
with m1: metric_card("Preco", fmt_currency_usd(spot), focal_q.get("change_pct"))
with m2:
    pos_str = f"{channel['position_pct']:.0f}%" if channel["is_valid"] else "n/d"
    hint = ""
    if channel["is_valid"]:
        if channel["position_pct"] > 85: hint = "⚠ topo do canal"
        elif channel["position_pct"] < 15: hint = "⚠ piso do canal"
    metric_card("Posicao no canal", pos_str, hint=hint)
with m3:
    metric_card("HV 20d", f"{hv20*100:.1f}%" if not np.isnan(hv20) else "n/d")
with m4:
    metric_card("IV Rank (proxy HV)", f"{iv_rank:.0f}")
with m5:
    metric_card("Variacao 20d", f"{change_20d:+.1f}%")

st.markdown("---")


# ── 3. Options flow (gate) ───────────────────────────────────────────────────
with st.spinner(f"Buscando option chain de {focal}..."):
    chain = opt_svc.get_chain(focal, max_expiries=6)

has_chain = chain["available"] and not (chain["calls"].empty and chain["puts"].empty)

if has_chain:
    section_header("Options Flow",
                   f"Agregado dos proximos {len(chain['expiries'])} vencimentos")

    o1, o2, o3, o4 = st.columns(4)
    with o1:
        pc = chain["pc_oi"]
        hint = "bearish" if pc > 1.1 else ("bullish" if pc < 0.7 else "neutro")
        metric_card("P/C ratio (OI)", f"{pc:.2f}", hint=hint)
    with o2:
        metric_card("P/C ratio (Volume)", f"{chain['pc_vol']:.2f}")
    with o3:
        metric_card("IV medio calls", f"{chain['iv_avg_calls']*100:.1f}%")
    with o4:
        metric_card("IV medio puts",  f"{chain['iv_avg_puts']*100:.1f}%")

    # GEX por strike
    gex_df = oa.calc_gex(chain, spot=spot)
    if not gex_df.empty:
        lo, hi = spot * 0.5, spot * 1.5
        g = gex_df[(gex_df["strike"] >= lo) & (gex_df["strike"] <= hi)].copy()
        if not g.empty:
            g["color"] = np.where(g["gex_total"] >= 0, COLOR_GREEN, COLOR_RED)
            fig_gex = go.Figure()
            fig_gex.add_trace(go.Bar(
                x=g["strike"], y=g["gex_total"],
                marker_color=g["color"], name="GEX total",
            ))
            fig_gex.add_vline(x=spot, line_color="#F0F0F0", line_dash="dash",
                              annotation_text=f"spot ${spot:.2f}",
                              annotation_position="top")
            fig_gex.update_layout(
                template="plotly_dark", height=340,
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
                st.caption("**GEX total positivo** — dealers tendem a estabilizar o preco "
                           "(vendem na alta, compram na queda).")
            else:
                st.caption("**GEX total negativo** — dealers tendem a amplificar movimentos "
                           "(compram na alta, vendem na queda). Maior potencial de volatilidade.")

    st.markdown("---")

else:
    st.info(f"Options chain nao disponivel para {focal}. "
            "Secoes de Options Flow e Simulador P&L ocultas.")


# ── 4. Simulador P&L (so com chain) ──────────────────────────────────────────
if has_chain:
    section_header("Simulador P&L — puts compradas",
                   "Tese bearish: 4 cenarios fixos + 3 bear progressivos customizaveis.")

    iv_base = chain["iv_avg"] or oa.IV_BASE_FALLBACK
    preset = oa.default_positions(focal, spot=spot, iv_base=iv_base)

    # Toggle — modo exploracao vs tracking operacional
    show_real = st.toggle(
        "💼 Tenho puts reais nesse ativo",
        value=st.session_state.get(f"tm_real_{focal}", False),
        help="Ative para configurar suas posicoes reais na sidebar e ver P&L calibrado. "
             "Desligado: mostra 1 put ATM teorica (exploracao).",
        key=f"tm_real_{focal}",
    )

    if show_real:
        with st.sidebar:
            st.markdown("---")
            st.markdown(f"**Thesis Monitor — puts em {focal}**")
            default_n = len(preset) if preset else 1
            n_legs = st.number_input("N de posicoes", min_value=1, max_value=6,
                                     value=int(default_n), step=1, key="tm_nlegs")

            positions: list[dict] = []
            for i in range(int(n_legs)):
                st.caption(f"**Put #{i+1}**")
                # Preset do ticker se existir, senao generico
                if i < len(preset):
                    strike_default   = preset[i]["strike"]
                    days_default     = preset[i]["days"]
                    contracts_default = preset[i]["contracts"]
                    prem_default     = preset[i]["premium_paid"]
                else:
                    strike_default   = round(spot * (0.9 - 0.05 * i), 2)
                    days_default     = 60 + 30 * i
                    contracts_default = 10
                    prem_default     = round(spot * 0.02, 2)

                k = st.number_input(f"Strike #{i+1}", value=float(strike_default),
                                    min_value=0.01, step=0.5, key=f"tm_k_{i}")
                d = st.number_input(f"Dias ate venc. #{i+1}", value=int(days_default),
                                    min_value=1, step=1, key=f"tm_d_{i}")
                c = st.number_input(f"Contratos #{i+1}", value=int(contracts_default),
                                    min_value=1, step=1, key=f"tm_c_{i}")
                p = st.number_input(
                    f"Premio pago #{i+1} (USD/acao)",
                    value=float(prem_default), min_value=0.0, step=0.05,
                    help="Ajuste para o premio efetivamente pago na sua corretora.",
                    key=f"tm_p_{i}",
                )
                positions.append({"strike": k, "days": d, "contracts": c, "premium_paid": p})

            st.caption("Cenarios bear customizaveis (spot):")
            c1 = st.number_input("Queda 20%", value=round(spot * 0.80, 2),
                                 min_value=0.01, step=0.5, key="tm_cs1")
            c2 = st.number_input("Bear base", value=round(spot * 0.70, 2),
                                 min_value=0.01, step=0.5, key="tm_cs2")
            c3 = st.number_input("Cauda",     value=round(spot * 0.55, 2),
                                 min_value=0.01, step=0.5, key="tm_cs3")
            custom_spots = [c1, c2, c3]
    else:
        # Modo exploracao: 1 put ATM teorica, sem inputs na sidebar
        positions    = preset if len(preset) == 1 else \
                       oa.default_positions("__generic__", spot=spot, iv_base=iv_base)
        custom_spots = [spot * 0.80, spot * 0.70, spot * 0.55]
        st.caption("ℹ Modo exploracao: 1 put ATM teorica. "
                   "Ative o toggle acima para configurar suas puts reais.")

    pnl_df = oa.pnl_scenarios(positions, spot=spot,
                              custom_spots=custom_spots, iv_base=iv_base)

    # Formatar para display
    disp = pnl_df.copy()
    disp["spot"]      = disp["spot"].map(lambda v: f"${v:,.2f}")
    disp["iv_used"]   = disp["iv_used"].map(lambda v: f"{v*100:.0f}%")
    disp["pnl_total"] = disp["pnl_total"].map(lambda v: f"${v:,.0f}")
    disp = disp.rename(columns={
        "scenario": "Cenario", "spot": "Spot", "iv_used": "IV usada",
        "pnl_total": "P&L total", "pnl_by_position": "Por posicao",
    })
    st.dataframe(disp, use_container_width=True, hide_index=True)
    st.caption(f"IV base (iv_avg do chain): **{iv_base*100:.0f}%** · "
               "ajustes automaticos: crash -20% → 65%, queda -10% → 55%, rally +10% → 35%")

    st.markdown("---")


# ── 5. Scorecard de convergencia ─────────────────────────────────────────────
section_header("Scorecard de convergencia",
               "Pilares do ativo focal · veredito quando >= 75% convergem")

tech_bias = oa.classify_technical(channel["position_pct"]) if channel["is_valid"] else None
mom_bias  = oa.classify_momentum(change_20d)
of_bias   = oa.classify_options_flow(chain["pc_oi"]) if has_chain else None
iv_label  = oa.classify_iv_rank(iv_rank)

sc = oa.scorecard(technical=tech_bias, momentum=mom_bias,
                  options_flow=of_bias, iv_rank_label=iv_label)

# Render chips
_colors = {"BEARISH": COLOR_RED, "BULLISH": COLOR_GREEN, "NEUTRAL": "#888"}
chip_html = ""
for p in sc["pillars"]:
    col = _colors[p["bias"]]
    chip_html += (f'<span style="display:inline-block;background:{col};'
                  f'color:#fff;font-size:0.72rem;font-weight:700;'
                  f'padding:4px 10px;border-radius:4px;margin-right:6px;'
                  f'letter-spacing:0.05em;">{p["name"]}: {p["bias"]}</span>')
# IV context
_iv_color = {"HIGH": "#C8232B", "LOW": "#26a269", "MID": "#888", "N/A": "#555"}[sc["iv_context"]]
chip_html += (f'<span style="display:inline-block;background:{_iv_color};'
              f'color:#fff;font-size:0.72rem;font-weight:700;'
              f'padding:4px 10px;border-radius:4px;'
              f'letter-spacing:0.05em;">IV Rank: {sc["iv_context"]}</span>')

st.markdown(f'<div style="margin:0.5rem 0 1rem 0;">{chip_html}</div>',
            unsafe_allow_html=True)

# Veredito
if sc["verdict"] == "STRONG_BEARISH":
    st.markdown(
        f'<div style="background:#2a1818;border-left:4px solid {COLOR_RED};'
        f'padding:0.9rem 1rem;border-radius:4px;">'
        f'<b style="color:{COLOR_RED};">⚠ CONVERGENCIA BEARISH FORTE</b> — '
        f'{sc["bearish_pct"]:.0f}% dos pilares avaliados apontam bearish.</div>',
        unsafe_allow_html=True)
elif sc["verdict"] == "STRONG_BULLISH":
    st.markdown(
        f'<div style="background:#182a18;border-left:4px solid {COLOR_GREEN};'
        f'padding:0.9rem 1rem;border-radius:4px;">'
        f'<b style="color:{COLOR_GREEN};">✓ CONVERGENCIA BULLISH FORTE</b> — '
        f'{sc["bullish_pct"]:.0f}% dos pilares avaliados apontam bullish.</div>',
        unsafe_allow_html=True)
else:
    st.caption(f"Sinais mistos · bearish {sc['bearish_pct']:.0f}% · "
               f"bullish {sc['bullish_pct']:.0f}% · sem convergencia forte.")

if not has_chain:
    st.caption("ℹ Scorecard calculado com 2 pilares (Tecnico + Momentum) — "
               "options chain indisponivel.")


render_footer()
