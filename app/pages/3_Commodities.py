import streamlit as st
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

st.set_page_config(page_title="Commodities | QUAD", page_icon="📦",
                   layout="wide", initial_sidebar_state="expanded")

from components.layout       import inject_css, render_sidebar, render_footer, page_header
from components.cards        import section_header, metric_card, error_card
from components.charts       import line_chart
from components.detail_panel import render_detail
from services                import yfinance_service as yf_svc
from services                import data_service     as data
from utils                   import fmt_currency_usd

TRIED = ["yfinance", "stooq"]

inject_css()
render_sidebar()
page_header("Commodities", "Energia, metais preciosos e agrícolas")

ENERGIA   = {"Petróleo Brent": "BZ=F"}
METAIS    = {"Ouro": "GC=F", "Prata": "SI=F", "Cobre": "HG=F", "Minério de Ferro": "TIO=F"}
AGRICOLAS = {"Soja": "ZS=F", "Milho": "ZC=F", "Trigo": "ZW=F", "Boi Gordo": "LE=F"}
ALL = {**ENERGIA, **METAIS, **AGRICOLAS}

HINTS = {
    "BZ=F":  ("USD/barril",  "Brent — principal referência global para o preço do petróleo"),
    "GC=F":  ("USD/oz troy", "Ouro — ativo de proteção contra inflação"),
    "SI=F":  ("USD/oz troy", "Prata — metal precioso e industrial"),
    "HG=F":  ("USD/lb",      "Cobre — termômetro da atividade industrial global"),
    "TIO=F": ("USD/t",       "Minério de Ferro 62% Fe CFR China — SGX Futures"),
    "ZS=F":  ("USD/bushel",  "Soja — principal grão de exportação do Brasil"),
    "ZC=F":  ("USD/bushel",  "Milho — base da alimentação animal e biocombustível"),
    "ZW=F":  ("USD/bushel",  "Trigo — impacto direto no preço do pão e alimentos"),
    "LE=F":  ("USD/cwt",     "Boi Gordo — futuro de gado vivo na CME"),
}

COLORS = {
    "BZ=F":  "#F5A623",
    "GC=F":  "#F5A623", "SI=F": "#9B9B9B", "HG=F": "#E07B39", "TIO=F": "#8B4513",
    "ZS=F":  "#26a269", "ZC=F": "#F5A623", "ZW=F": "#D4A017", "LE=F":  "#A0522D",
}

with st.spinner("Carregando commodities..."):
    quotes = data.quotes(list(ALL.values()))
    hists  = {t: data.history(t, period="6mo") for t in ALL.values()}


def _card(col, label, ticker):
    q = quotes.get(ticker, {})
    hint, tooltip = HINTS.get(ticker, ("", ""))
    with col:
        if q.get("error") or q.get("price") is None:
            error_card(label, tried=TRIED)
        else:
            metric_card(label, fmt_currency_usd(q["price"]),
                        q.get("change_pct"), hint=hint, tooltip=tooltip)


def _chart(df, label, ticker, height=200):
    if df.empty or "Close" not in df.columns:
        st.caption("Histórico indisponível.")
        return
    d = df.reset_index()
    date_col = "Date" if "Date" in d.columns else d.columns[0]
    fig = line_chart(d, x_col=date_col, y_col="Close",
                     title=f"{label} — 6m", y_label="USD",
                     color=COLORS.get(ticker, "#C8232B"),
                     fill=True, height=height)
    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})


# ══ ENERGIA ══════════════════════════════════════════════════════════════════
section_header("Energia", "Petróleo Brent")
c1, _ = st.columns([1, 1])
_card(c1, "Petróleo Brent", "BZ=F")

st.markdown("<br>", unsafe_allow_html=True)
ch1, _ = st.columns([1, 1])
with ch1: _chart(hists["BZ=F"], "Brent", "BZ=F", height=220)

st.markdown("---")


# ══ METAIS ════════════════════════════════════════════════════════════════════
section_header("Metais Preciosos & Industriais", "Ouro, Prata, Cobre e Minério de Ferro")
c1, c2, c3, c4 = st.columns(4)
_card(c1, "Ouro",             "GC=F")
_card(c2, "Prata",            "SI=F")
_card(c3, "Cobre",            "HG=F")
_card(c4, "Minério de Ferro", "TIO=F")

st.markdown("<br>", unsafe_allow_html=True)
ch1, ch2, ch3, ch4 = st.columns(4)
with ch1: _chart(hists["GC=F"],  "Ouro",             "GC=F",  height=200)
with ch2: _chart(hists["SI=F"],  "Prata",            "SI=F",  height=200)
with ch3: _chart(hists["HG=F"],  "Cobre",            "HG=F",  height=200)
with ch4: _chart(hists["TIO=F"], "Minério de Ferro", "TIO=F", height=200)

st.markdown("---")


# ══ AGRÍCOLAS ════════════════════════════════════════════════════════════════
section_header("Agrícolas", "Soja, Milho, Trigo e Boi Gordo")
c1, c2, c3, c4 = st.columns(4)
_card(c1, "Soja",     "ZS=F")
_card(c2, "Milho",    "ZC=F")
_card(c3, "Trigo",    "ZW=F")
_card(c4, "Boi Gordo","LE=F")

st.markdown("<br>", unsafe_allow_html=True)
ch1, ch2, ch3, ch4 = st.columns(4)
with ch1: _chart(hists["ZS=F"], "Soja",     "ZS=F", height=180)
with ch2: _chart(hists["ZC=F"], "Milho",    "ZC=F", height=180)
with ch3: _chart(hists["ZW=F"], "Trigo",    "ZW=F", height=180)
with ch4: _chart(hists["LE=F"], "Boi Gordo","LE=F", height=180)


# ── Detalhe por ticker ────────────────────────────────────────────────────────
render_detail(ALL, currency="USD", period_default="6mo")

render_footer()
