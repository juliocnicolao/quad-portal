import streamlit as st
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

st.set_page_config(page_title="Cripto | QUAD", page_icon="🪙",
                   layout="wide", initial_sidebar_state="expanded")

from components.layout import inject_css, render_sidebar, render_footer, page_header
from components.cards  import section_header, metric_card, error_card
from components.charts import line_chart, multi_line_chart  # multi_line_chart restaurado em charts.py
from services          import yfinance_service as yf_svc
from utils             import fmt_currency_usd, fmt_pct
import requests
import pandas as pd

inject_css()
render_sidebar()
page_header("Cripto", "Bitcoin, Ethereum e mercado global de criptoativos")


# ── Fetch ─────────────────────────────────────────────────────────────────────
@st.cache_data(ttl=900)
def get_crypto_global():
    try:
        r = requests.get(
            "https://api.coingecko.com/api/v3/global", timeout=8
        )
        r.raise_for_status()
        d = r.json()["data"]
        return {
            "btc_dominance":  d["market_cap_percentage"].get("btc"),
            "eth_dominance":  d["market_cap_percentage"].get("eth"),
            "total_mcap_usd": d["total_market_cap"].get("usd"),
            "mcap_change_24h": d.get("market_cap_change_percentage_24h_usd"),
        }
    except Exception:
        return {}

@st.cache_data(ttl=900)
def _hist(ticker, period="1y"):
    return yf_svc.get_history(ticker, period=period)


with st.spinner("Carregando criptoativos..."):
    btc       = yf_svc.get_quote("BTC-USD")
    eth       = yf_svc.get_quote("ETH-USD")
    bnb       = yf_svc.get_quote("BNB-USD")
    sol       = yf_svc.get_quote("SOL-USD")
    global_d  = get_crypto_global()
    hist_btc  = _hist("BTC-USD")
    hist_eth  = _hist("ETH-USD")


# ── Hero cards ────────────────────────────────────────────────────────────────
section_header("Principais Criptoativos", "Preços em USD com variação do dia")
c1, c2, c3, c4 = st.columns(4)

def _card(col, label, q, hint="", tooltip=""):
    with col:
        if q.get("error") or q.get("price") is None:
            error_card(label)
        else:
            metric_card(label, fmt_currency_usd(q["price"]),
                        q.get("change_pct"), hint=hint, tooltip=tooltip)

_card(c1, "Bitcoin (BTC)",  btc, "BTC/USD",
      "A maior criptomoeda por capitalização de mercado")
_card(c2, "Ethereum (ETH)", eth, "ETH/USD",
      "Plataforma de contratos inteligentes e DeFi")
_card(c3, "BNB",            bnb, "BNB/USD",
      "Token nativo da Binance Smart Chain")
_card(c4, "Solana (SOL)",   sol, "SOL/USD",
      "Blockchain de alta velocidade e baixo custo")

st.markdown("---")


# ── Dominância e Market Cap ───────────────────────────────────────────────────
section_header("Mercado Global de Cripto", "Capitalização e dominância")

if global_d:
    g1, g2, g3, g4 = st.columns(4)

    def _gmcap(val):
        if val is None: return "—"
        return f"$ {val/1e12:.2f}T" if val >= 1e12 else f"$ {val/1e9:.1f}B"

    with g1:
        metric_card("Market Cap Total", _gmcap(global_d.get("total_mcap_usd")),
                    global_d.get("mcap_change_24h"),
                    hint="Var. 24h",
                    tooltip="Capitalização total de todos os criptoativos")
    with g2:
        btc_dom = global_d.get("btc_dominance")
        metric_card("Dominância BTC",
                    f"{btc_dom:.1f}%" if btc_dom else "—",
                    hint="% do market cap total",
                    tooltip="Quanto o Bitcoin representa do total do mercado cripto")
    with g3:
        eth_dom = global_d.get("eth_dominance")
        metric_card("Dominância ETH",
                    f"{eth_dom:.1f}%" if eth_dom else "—",
                    hint="% do market cap total",
                    tooltip="Quanto o Ethereum representa do total do mercado cripto")
    with g4:
        others = 100 - (global_d.get("btc_dominance") or 0) - (global_d.get("eth_dominance") or 0)
        metric_card("Altcoins",
                    f"{others:.1f}%",
                    hint="% restante do mercado",
                    tooltip="Participação de todas as outras criptomoedas no mercado")

    # Gráfico de pizza de dominância
    import plotly.graph_objects as go
    btc_d = global_d.get("btc_dominance", 0)
    eth_d = global_d.get("eth_dominance", 0)
    rest  = max(0, 100 - btc_d - eth_d)

    fig_pie = go.Figure(go.Pie(
        labels=["Bitcoin", "Ethereum", "Altcoins"],
        values=[btc_d, eth_d, rest],
        hole=0.55,
        marker_colors=["#F7931A", "#627EEA", "#888888"],
        textinfo="label+percent",
        hovertemplate="%{label}: <b>%{value:.1f}%</b><extra></extra>",
    ))
    fig_pie.update_layout(
        paper_bgcolor="#0D0D0D",
        font=dict(color="#F0F0F0", size=12),
        legend=dict(bgcolor="rgba(0,0,0,0)"),
        margin=dict(l=10, r=10, t=30, b=10),
        height=240,
        title=dict(text="Dominância de Mercado", font=dict(size=13, color="#888")),
        annotations=[dict(text="Cripto", x=0.5, y=0.5, font_size=14,
                          font_color="#F0F0F0", showarrow=False)],
    )
    _, pie_col, _ = st.columns([1, 2, 1])
    with pie_col:
        st.plotly_chart(fig_pie, use_container_width=True, config={"displayModeBar": False})

else:
    st.warning("Dados globais de mercado indisponíveis (CoinGecko).")

st.markdown("---")


# ── Gráficos históricos ───────────────────────────────────────────────────────
section_header("Histórico de Preços", "Últimos 12 meses em USD")

periodo = st.radio("Período:", ["3 meses", "6 meses", "1 ano"],
                   index=2, horizontal=True, label_visibility="collapsed")
_p_map = {"3 meses": "3mo", "6 meses": "6mo", "1 ano": "1y"}
_p = _p_map[periodo]

@st.cache_data(ttl=900)
def _h(t, p): return yf_svc.get_history(t, period=p)

h_btc = _h("BTC-USD", _p)
h_eth = _h("ETH-USD", _p)

col_btc, col_eth = st.columns(2)

def _date_col(df):
    """Return the name of the date column after reset_index()."""
    for c in ["Date", "Datetime", "index"]:
        if c in df.columns:
            return c
    return df.columns[0]

with col_btc:
    if not h_btc.empty and "Close" in h_btc.columns:
        d = h_btc.reset_index()
        fig = line_chart(d, x_col=_date_col(d), y_col="Close",
                         title=f"Bitcoin — {periodo}",
                         y_label="USD", color="#F7931A", fill=True, height=280)
        st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})

with col_eth:
    if not h_eth.empty and "Close" in h_eth.columns:
        d = h_eth.reset_index()
        fig = line_chart(d, x_col=_date_col(d), y_col="Close",
                         title=f"Ethereum — {periodo}",
                         y_label="USD", color="#627EEA", fill=True, height=280)
        st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})

# Performance relativa BTC vs ETH
if not h_btc.empty and not h_eth.empty and "Close" in h_btc.columns:
    st.markdown("<br>", unsafe_allow_html=True)
    section_header("Performance Relativa", "BTC vs ETH (base 100)")
    btc_n = (h_btc["Close"] / h_btc["Close"].iloc[0] * 100).reset_index()
    eth_n = (h_eth["Close"] / h_eth["Close"].iloc[0] * 100).reset_index()
    dc_b  = _date_col(btc_n)
    dc_e  = _date_col(eth_n)
    fig = multi_line_chart(
        series=[
            {"name": "Bitcoin",  "x": btc_n[dc_b], "y": btc_n["Close"], "color": "#F7931A"},
            {"name": "Ethereum", "x": eth_n[dc_e], "y": eth_n["Close"], "color": "#627EEA"},
        ],
        title=f"Retorno relativo — {periodo} (base 100)",
        y_label="Base 100",
        height=260,
    )
    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})

render_footer()
