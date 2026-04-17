import streamlit as st
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

st.set_page_config(page_title="Commodities | QUAD", page_icon="📦",
                   layout="wide", initial_sidebar_state="expanded")

from components.layout       import inject_css, render_sidebar, render_footer, page_header
from components.cards        import section_header, metric_card, error_card, format_age
from components.charts       import line_chart
from components.detail_panel import render_detail
from services                import yfinance_service as yf_svc
from services                import data_service     as data
from services                import awesome_service  as fx_svc
from utils                   import fmt_currency_usd, fmt_currency_brl

TRIED = ["yfinance", "stooq"]

_fx       = fx_svc.get_fx(["USD-BRL"]).get("USD-BRL", {})
_usd_brl  = _fx.get("mid") or _fx.get("bid")
_show_brl = bool(st.session_state.get("show_brl_equiv")) and _usd_brl

def _brl_equiv(usd_value):
    if not _show_brl or usd_value is None:
        return None
    return fmt_currency_brl(usd_value * _usd_brl)

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
                        q.get("change_pct"), hint=hint, tooltip=tooltip,
                        subvalue=_brl_equiv(q["price"]))


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
_sources = sorted({q.get("source") for q in quotes.values() if q.get("source") and q.get("source") != "none"})
_age = format_age(max((q.get("fetched_at") or 0) for q in quotes.values()))
section_header("Energia", "Petróleo Brent",
               timestamp=_age, source=" · ".join(_sources) if _sources else None)
c1, _ = st.columns([1, 1])
_card(c1, "Petróleo Brent", "BZ=F")

st.markdown("<br>", unsafe_allow_html=True)
ch1, _ = st.columns([1, 1])
with ch1: _chart(hists["BZ=F"], "Brent", "BZ=F", height=220)

st.markdown("---")


# ══ METAIS ════════════════════════════════════════════════════════════════════
section_header("Metais Preciosos & Industriais",
               "Ouro (USD/oz e R$/g), Prata, Cobre e Minério de Ferro")
c1, c2, c3, c4, c5 = st.columns(5)
_card(c1, "Ouro (USD/oz)",    "GC=F")

# ── Ouro em R$/grama (conversão: USD/oz × USD-BRL ÷ 31.1035 g/oz) ────────────
_OZ_TO_G  = 31.1034768   # troy ounce → gramas
_ouro_q   = quotes.get("GC=F", {})
_ouro_usd = _ouro_q.get("price")
_ouro_pct = _ouro_q.get("change_pct")
_ouro_brl_g = (_ouro_usd * _usd_brl / _OZ_TO_G) if (_ouro_usd and _usd_brl) else None

with c2:
    if _ouro_brl_g is None:
        error_card("Ouro (R$/g)", tried=TRIED + ["usd-brl"])
    else:
        metric_card(
            "Ouro (R$/g)",
            fmt_currency_brl(_ouro_brl_g),
            _ouro_pct,                     # var. dia do ouro em USD (bom proxy)
            hint="BRL/grama",
            tooltip="Ouro convertido: (USD/oz × USD-BRL) ÷ 31,1035 g/oz. "
                    "Var. dia reflete o ouro em dólar (não inclui variação do câmbio no dia).",
        )

_card(c3, "Prata",            "SI=F")
_card(c4, "Cobre",            "HG=F")
_card(c5, "Minério de Ferro", "TIO=F")

st.markdown("<br>", unsafe_allow_html=True)
ch1, ch2, ch3, ch4, ch5 = st.columns(5)
with ch1: _chart(hists["GC=F"],  "Ouro (USD/oz)",    "GC=F",  height=200)

# Gráfico Ouro R$/g: usa histórico de GC=F e aplica câmbio spot atual (aproximação)
# — fiel ao dia a dia porque só multiplicamos pela USDBRL corrente do histórico
with ch2:
    _dfg = hists.get("GC=F")
    if _dfg is None or _dfg.empty or "Close" not in _dfg.columns or not _usd_brl:
        st.caption("Histórico em R$/g indisponível.")
    else:
        import pandas as pd
        _usdbrl_hist = data.history("USDBRL=X", period="6mo")
        d = _dfg.reset_index()
        date_col = "Date" if "Date" in d.columns else d.columns[0]
        d = d[[date_col, "Close"]].rename(columns={"Close": "gold_usd"})
        if not _usdbrl_hist.empty and "Close" in _usdbrl_hist.columns:
            fx_df = _usdbrl_hist.reset_index()
            fx_col = "Date" if "Date" in fx_df.columns else fx_df.columns[0]
            fx_df = fx_df[[fx_col, "Close"]].rename(columns={fx_col: date_col, "Close": "usdbrl"})
            d = pd.merge_asof(
                d.sort_values(date_col), fx_df.sort_values(date_col),
                on=date_col, direction="backward",
            )
            d["Close"] = d["gold_usd"] * d["usdbrl"] / _OZ_TO_G
        else:
            # fallback: câmbio atual constante
            d["Close"] = d["gold_usd"] * _usd_brl / _OZ_TO_G
        d = d.dropna(subset=["Close"])
        fig = line_chart(d, x_col=date_col, y_col="Close",
                         title="Ouro (R$/g) — 6m", y_label="R$/g",
                         color="#D4AF37", fill=True, height=200)
        st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})

with ch3: _chart(hists["SI=F"],  "Prata",            "SI=F",  height=200)
with ch4: _chart(hists["HG=F"],  "Cobre",            "HG=F",  height=200)
with ch5: _chart(hists["TIO=F"], "Minério de Ferro", "TIO=F", height=200)

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
