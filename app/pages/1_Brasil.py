import streamlit as st
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

st.set_page_config(page_title="Brasil | QUAD", page_icon="🌎",
                   layout="wide", initial_sidebar_state="expanded")

from components.layout      import inject_css, render_sidebar, render_footer, page_header
from components.cards       import section_header, metric_card, error_card
from components.charts      import line_chart, bar_movers
from components.detail_panel import render_detail
from services               import brapi_service as brapi
from services               import yfinance_service as yf_svc
from services               import stooq_service    as stooq
from services               import bcb_service as bcb
from utils                  import fmt_points, fmt_pct
import plotly.graph_objects as go
import pandas as pd

inject_css()
render_sidebar()
page_header("Brasil", "Bolsa, inflação e principais ações")

TICKERS = [
    "PETR4","VALE3","ITUB4","BBDC4","B3SA3",
    "ABEV3","WEGE3","RENT3","ELET3","SUZB3",
    "MGLU3","BBAS3","CPLE6","JBSS3","GGBR4",
    "CSNA3","EMBR3","LREN3","HAPV3","RADL3",
]

with st.spinner("Carregando dados do Brasil..."):
    # Cascata: brapi → yfinance → stooq
    ibov = brapi.get_quote("^BVSP")
    if ibov.get("error") or ibov.get("price") is None:
        ibov = yf_svc.get_quote("^BVSP")
    if ibov.get("error") or ibov.get("price") is None:
        ibov = stooq.get_quote("^BVSP")

    ibov_hist = yf_svc.get_history("^BVSP", period="1y")
    if ibov_hist.empty:
        ibov_hist = stooq.get_history("^BVSP", period="1y")

    ipca_hist = bcb.get_ipca_history(n=24)
    quotes    = brapi.get_quotes(TICKERS)


# ── Ibovespa hero ─────────────────────────────────────────────────────────────
section_header("Ibovespa", "Índice da Bolsa de Valores do Brasil — B3")
col_card, col_chart = st.columns([1, 3])

with col_card:
    if ibov["price"]:
        metric_card("Ibovespa", f"{fmt_points(ibov['price'])} pts",
                    ibov.get("change_pct"), hint="Variação do dia",
                    tooltip="Índice das ações mais negociadas da B3")
        st.markdown("<br>", unsafe_allow_html=True)
        st.caption("O Ibovespa é o principal indicador de desempenho "
                   "das ações negociadas na B3.")
    else:
        error_card("Ibovespa")

with col_chart:
    if not ibov_hist.empty and "Close" in ibov_hist.columns:
        df = ibov_hist.reset_index()
        date_col = "Date" if "Date" in df.columns else df.columns[0]
        fig = line_chart(df, x_col=date_col, y_col="Close",
                         title="Ibovespa — 12 meses", y_label="Pontos",
                         color="#C8232B", height=240)
        st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
    else:
        st.warning("Histórico Ibovespa indisponível.")

st.markdown("---")


# ── IPCA Histórico ────────────────────────────────────────────────────────────
section_header("IPCA — Inflação Mensal", "Variação % mês a mês — últimos 24 meses")

if not ipca_hist.empty:
    colors = ["#26a269" if v >= 0 else "#C8232B" for v in ipca_hist["valor"]]
    fig = go.Figure(go.Bar(
        x=ipca_hist["data"].dt.strftime("%b/%y"),
        y=ipca_hist["valor"],
        marker_color=colors,
        text=ipca_hist["valor"].map(lambda v: f"{v:.2f}%"),
        textposition="outside",
        hovertemplate="%{x}: <b>%{y:.2f}%</b><extra>IPCA</extra>",
    ))
    fig.update_layout(
        paper_bgcolor="#0D0D0D", plot_bgcolor="#1A1A1A",
        font=dict(color="#F0F0F0", size=11),
        margin=dict(l=10, r=10, t=30, b=10),
        xaxis=dict(gridcolor="#2a2a2a", tickangle=-45),
        yaxis=dict(gridcolor="#2a2a2a", ticksuffix="%"),
        height=280,
        title=dict(text="IPCA Mensal (%)", font=dict(size=13, color="#888")),
    )
    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})

    acum_12m = ipca_hist.tail(12)["valor"].sum()
    acum_24m = ipca_hist["valor"].sum()
    ultimo   = ipca_hist.iloc[-1]
    c1, c2, c3 = st.columns(3)
    with c1:
        metric_card("IPCA Acum. 12m", f"{acum_12m:.2f}%",
                    hint="Últimos 12 meses",
                    tooltip="Inflação oficial acumulada nos últimos 12 meses")
    with c2:
        metric_card("IPCA Acum. 24m", f"{acum_24m:.2f}%", hint="Últimos 24 meses")
    with c3:
        metric_card("Último IPCA", f"{ultimo['valor']:.2f}%",
                    hint=ultimo["data"].strftime("%b/%Y"))
else:
    st.warning("Histórico IPCA indisponível.")

st.markdown("---")


# ── Top Movers ────────────────────────────────────────────────────────────────
section_header("Top Movers", "Maiores altas e baixas do dia")

valid = [
    {"ticker": t, **q}
    for t, q in quotes.items()
    if not q.get("error") and q.get("change_pct") is not None
]

if valid:
    df_movers = pd.DataFrame(valid).sort_values("change_pct", ascending=False)
    top5_up   = df_movers.head(5)
    top5_down = df_movers.tail(5).sort_values("change_pct")
    col_up, col_down = st.columns(2)
    with col_up:
        fig = bar_movers(top5_up, "ticker", "change_pct", "▲ Maiores Altas", 240)
        st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
    with col_down:
        fig = bar_movers(top5_down, "ticker", "change_pct", "▼ Maiores Baixas", 240)
        st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})

st.markdown("---")


# ── Top Ativos por Liquidez ───────────────────────────────────────────────────
section_header("Top Ativos — Liquidez", "Volume financeiro médio (3 meses)")

LIQUID = ["PETR4","VALE3","ITUB4","BBDC4","BBAS3",
          "B3SA3","ELET3","WEGE3","ABEV3","SUZB3"]

import yfinance as yf

@st.cache_data(ttl=900)
def _get_volume(tickers):
    rows = []
    for t in tickers:
        try:
            fi = yf.Ticker(t + ".SA").fast_info
            rows.append({"Ativo": t, "_price": fi.last_price or 0,
                         "_vol": fi.three_month_average_volume or 0})
        except Exception:
            rows.append({"Ativo": t, "_price": 0, "_vol": 0})
    return rows

rows = _get_volume(LIQUID)
df_liq = pd.DataFrame(rows).sort_values("_vol", ascending=False)
df_liq["Preço"]         = df_liq["_price"].map(lambda v: f"R$ {v:.2f}" if v else "—")
df_liq["Vol. Médio 3m"] = df_liq["_vol"].map(
    lambda v: f"{v/1e6:.1f}M" if v >= 1e6 else f"{v/1e3:.0f}K" if v else "—")
df_liq["Var. Dia"]      = df_liq["Ativo"].map(
    lambda t: fmt_pct(quotes[t]["change_pct"])
    if t in quotes and not quotes[t].get("error")
    and quotes[t].get("change_pct") is not None else "—")

st.dataframe(df_liq[["Ativo","Preço","Var. Dia","Vol. Médio 3m"]],
             use_container_width=True, hide_index=True)


# ── Detalhe por ticker ────────────────────────────────────────────────────────
BR_DETAIL = {t: t + ".SA" for t in TICKERS}
BR_DETAIL["Ibovespa"] = "^BVSP"
render_detail(BR_DETAIL, currency="BRL", period_default="6mo")

render_footer()
