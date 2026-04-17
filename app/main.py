import streamlit as st

st.set_page_config(
    page_title="Portal Global | QUAD Wealth Management",
    page_icon="🔴",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Global CSS ────────────────────────────────────────────────────────────────
st.markdown("""
<style>
[data-testid="stSidebarNav"] { display: none !important; }
.block-container { padding-top: 2.5rem !important; padding-bottom: 3.5rem; }

.quad-brand {
    text-align: center;
    padding: 1rem 0 1.5rem 0;
    border-bottom: 1px solid #2a2a2a;
    margin-bottom: 1rem;
}
.quad-brand .brand-name {
    font-size: 1.1rem; font-weight: 700; color: #F0F0F0;
    letter-spacing: 0.08em; text-transform: uppercase;
}
.quad-brand .brand-sub {
    font-size: 0.7rem; color: #888;
    letter-spacing: 0.12em; text-transform: uppercase;
}

.page-title {
    font-size: 1.6rem; font-weight: 700;
    color: #F0F0F0; margin-bottom: 0.1rem;
}
.page-subtitle { font-size: 0.8rem; color: #666; margin-bottom: 1.5rem; }

.metric-card {
    background: #1A1A1A; border: 1px solid #2a2a2a;
    border-radius: 8px; padding: 1rem 1.2rem; text-align: left;
    height: 100%;
}
.metric-card .card-label {
    font-size: 0.7rem; color: #888; text-transform: uppercase;
    letter-spacing: 0.1em; margin-bottom: 0.25rem;
}
.metric-card .card-value {
    font-size: 1.5rem; font-weight: 700;
    color: #F0F0F0; line-height: 1.1;
}
.metric-card .card-delta-pos { font-size: 0.85rem; color: #26a269; font-weight: 600; }
.metric-card .card-delta-neg { font-size: 0.85rem; color: #C8232B; font-weight: 600; }
.metric-card .card-hint { font-size: 0.65rem; color: #555; margin-top: 0.3rem; }

.portal-footer {
    position: fixed; bottom: 0; left: 0; right: 0;
    background: #0D0D0D; border-top: 1px solid #1f1f1f;
    text-align: center; padding: 0.4rem;
    font-size: 0.65rem; color: #444; z-index: 999;
}

hr { border-color: #2a2a2a; }

.fx-table { width: 100%; border-collapse: collapse; font-size: 0.85rem; }
.fx-table th {
    color: #888; font-size: 0.65rem; text-transform: uppercase;
    letter-spacing: 0.08em; padding: 0.4rem 0.6rem;
    border-bottom: 1px solid #2a2a2a; text-align: left;
}
.fx-table td { padding: 0.45rem 0.6rem; border-bottom: 1px solid #1f1f1f; color: #F0F0F0; }
.fx-table tr:hover td { background: #1f1f1f; }
.pos { color: #26a269; font-weight: 600; }
.neg { color: #C8232B; font-weight: 600; }
</style>
""", unsafe_allow_html=True)


# ── Imports ───────────────────────────────────────────────────────────────────
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from components.cards  import metric_card, section_header, error_card, freshness_badge
from components.charts import line_chart, yield_curve_chart
from services          import yfinance_service as yf_svc
from services          import brapi_service    as brapi
from services          import awesome_service  as fx_svc
from services          import bcb_service      as bcb
from services          import stooq_service    as stooq
from services          import data_service     as data
from utils             import fmt_currency_brl, fmt_currency_usd, fmt_points, fmt_pct


# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("""
    <div class="quad-brand">
        <div style="font-size:2rem;font-weight:900;color:#C8232B;letter-spacing:-0.02em;">Q</div>
        <div class="brand-name">QUAD Wealth</div>
        <div class="brand-sub">Portal Global</div>
    </div>
    """, unsafe_allow_html=True)

    st.markdown("**Navegação**")
    st.page_link("main.py",                   label="Visão Geral",  icon="📊")
    st.page_link("pages/1_Brasil.py",         label="Brasil",       icon="🌎")
    st.page_link("pages/2_Global.py",         label="Global",       icon="🌐")
    st.page_link("pages/3_Commodities.py",    label="Commodities",  icon="📦")
    st.page_link("pages/4_Cripto.py",         label="Cripto",       icon="🪙")
    st.page_link("pages/5_Fundamentos.py",    label="Fundamentos",  icon="🌍")
    st.markdown("---")
    st.caption("Dados com atraso de até 15 min.")


# ── Page header ───────────────────────────────────────────────────────────────
st.markdown('<div class="page-title">Visão Geral</div>', unsafe_allow_html=True)
st.markdown('<div class="page-subtitle">Panorama dos principais mercados — atualizado a cada 15 minutos</div>',
            unsafe_allow_html=True)


# ── Data fetch (all cached) ───────────────────────────────────────────────────
TRIED = ["brapi", "yfinance", "stooq"]

with st.spinner("Carregando dados..."):
    ibov  = data.quote("^BVSP", br=True)       # brapi → yfinance → stooq
    sp500 = data.quote("^GSPC")
    btc   = data.quote("BTC-USD")
    wti   = data.quote("CL=F")
    ouro  = data.quote("GC=F")
    selic = bcb.get_selic()
    ipca  = bcb.get_ipca_12m()
    fx_data = fx_svc.get_fx(["USD-BRL", "EUR-BRL", "GBP-BRL", "ARS-BRL", "CHF-BRL", "JPY-BRL"])
    # Fallback FX: se USD-BRL falhar, busca via yfinance/stooq
    if fx_data.get("USD-BRL", {}).get("error"):
        dolar_yf = data.quote("USDBRL=X")
        if dolar_yf.get("price"):
            fx_data["USD-BRL"] = {
                "bid":        dolar_yf["price"],
                "mid":        dolar_yf["price"],
                "change_pct": dolar_yf.get("change_pct"),
                "error":      False,
            }
    ibov_hist  = data.history("^BVSP",    period="6mo")
    dolar_hist = data.history("USDBRL=X", period="6mo")


# ── Row 1: Hero cards ─────────────────────────────────────────────────────────
section_header("Mercados", "Principais índices e ativos")
c1, c2, c3, c4, c5, c6 = st.columns(6)

def _card(col, label, value, change_pct, hint=None, tooltip=None):
    with col:
        if value is None:
            error_card(label, tried=TRIED)
        else:
            metric_card(label, value, change_pct, hint, tooltip)

_card(c1, "Ibovespa",
      fmt_points(ibov["price"]) + " pts" if ibov["price"] else None,
      ibov.get("change_pct"),
      hint="B3 — Brasil",
      tooltip="Índice das maiores empresas da bolsa brasileira")

_card(c2, "Dólar (USD)",
      fmt_currency_brl(fx_data.get("USD-BRL", {}).get("bid", 0)) if "USD-BRL" in fx_data and not fx_data["USD-BRL"].get("error") else None,
      fx_data.get("USD-BRL", {}).get("change_pct"),
      hint="BRL/USD",
      tooltip="Taxa de câmbio dólar americano × real brasileiro")

_card(c3, "Selic",
      f"{selic['value']:.2f}% a.a." if selic["value"] else None,
      None,
      hint="Taxa básica de juros",
      tooltip="Taxa Selic Meta definida pelo Banco Central do Brasil")

_card(c4, "S&P 500",
      fmt_points(sp500["price"]) + " pts" if sp500["price"] else None,
      sp500.get("change_pct"),
      hint="EUA — NYSE/Nasdaq",
      tooltip="Índice das 500 maiores empresas americanas")

_card(c5, "Bitcoin",
      fmt_currency_usd(btc["price"]) if btc["price"] else None,
      btc.get("change_pct"),
      hint="BTC/USD",
      tooltip="Preço do Bitcoin em dólares americanos")

_card(c6, "Petróleo WTI",
      fmt_currency_usd(wti["price"]) if wti["price"] else None,
      wti.get("change_pct"),
      hint="Futuro WTI",
      tooltip="Contrato futuro de petróleo West Texas Intermediate")


st.markdown("<br>", unsafe_allow_html=True)


# ── Row 2: Mini charts ────────────────────────────────────────────────────────
section_header("Evolução Recente", "Últimos 6 meses")
ch1, ch2 = st.columns(2)

with ch1:
    if not ibov_hist.empty:
        df_ibov = ibov_hist.reset_index()
        fig = line_chart(df_ibov, x_col="Date", y_col="Close",
                         title="Ibovespa — 6 meses", y_label="Pontos",
                         color="#C8232B", height=260)
        st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
    else:
        st.warning("Histórico Ibovespa indisponível.")

with ch2:
    if not dolar_hist.empty:
        df_dolar = dolar_hist.reset_index()
        fig = line_chart(df_dolar, x_col="Date", y_col="Close",
                         title="Dólar (USD/BRL) — 6 meses", y_label="R$",
                         color="#4A90D9", height=260)
        st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
    else:
        st.warning("Histórico do Dólar indisponível.")


# ── Row 3: FX table + Macro pills ─────────────────────────────────────────────
fx_col, macro_col = st.columns([3, 2])

with fx_col:
    section_header("Câmbio", "Moedas × Real Brasileiro")

    FX_LABELS = {
        "USD-BRL": ("Dólar Americano", "🇺🇸"),
        "EUR-BRL": ("Euro",            "🇪🇺"),
        "GBP-BRL": ("Libra Esterlina", "🇬🇧"),
        "ARS-BRL": ("Peso Argentino",  "🇦🇷"),
        "CHF-BRL": ("Franco Suíço",    "🇨🇭"),
        "JPY-BRL": ("Iene Japonês",    "🇯🇵"),
    }

    rows_html = ""
    for pair, (name, flag) in FX_LABELS.items():
        d = fx_data.get(pair, {})
        if d.get("error") or not d.get("mid"):
            continue
        mid   = f"R$ {d['mid']:.4f}"
        pct   = d.get("change_pct", 0)
        arrow = "▲" if pct >= 0 else "▼"
        css   = "pos" if pct >= 0 else "neg"
        rows_html += f"""
        <tr>
            <td>{flag} {name}</td>
            <td><b>{mid}</b></td>
            <td class="{css}">{arrow} {pct:+.2f}%</td>
        </tr>"""

    st.markdown(f"""
    <table class="fx-table">
        <thead><tr><th>Moeda</th><th>Cotação</th><th>Var. Dia</th></tr></thead>
        <tbody>{rows_html}</tbody>
    </table>
    """, unsafe_allow_html=True)

with macro_col:
    section_header("Macro Brasil", "Indicadores-chave")

    def _macro_pill(label: str, value, unit: str, tooltip: str = ""):
        if value is None:
            st.markdown(f"""
            <div class="metric-card" style="margin-bottom:0.6rem;opacity:0.4;">
                <div class="card-label">{label}</div>
                <div class="card-value" style="font-size:1rem;color:#666;">—</div>
            </div>""", unsafe_allow_html=True)
        else:
            st.markdown(f"""
            <div class="metric-card" style="margin-bottom:0.6rem;" title="{tooltip}">
                <div class="card-label">{label}</div>
                <div class="card-value" style="font-size:1.3rem;">{value:.2f}<span style="font-size:0.8rem;color:#888;margin-left:4px;">{unit}</span></div>
            </div>""", unsafe_allow_html=True)

    _macro_pill("Selic Meta",   selic["value"],  "% a.a.",
                "Taxa básica de juros definida pelo Banco Central")
    _macro_pill("IPCA 12 meses", ipca["value"],  "%",
                "Inflação oficial acumulada nos últimos 12 meses")
    _macro_pill("Ouro (Spot)",  ouro["price"],   "USD/oz",
                "Preço à vista do ouro em dólares por onça troy")


# ── Footer ────────────────────────────────────────────────────────────────────
st.markdown("""
<div class="portal-footer">
    Dados com atraso de até 15 minutos — não utilize para decisões de trading. &nbsp;|&nbsp;
    QUAD Wealth Management © 2024
</div>
""", unsafe_allow_html=True)
