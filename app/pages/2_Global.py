import streamlit as st
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

st.set_page_config(page_title="Global | QUAD", page_icon="🌐",
                   layout="wide", initial_sidebar_state="expanded")

from components.layout       import inject_css, render_sidebar, render_footer, page_header
from components.cards        import section_header, metric_card, error_card, format_age
from components.charts       import yield_curve_chart, line_chart
from components.detail_panel import render_detail
from services                import yfinance_service as yf_svc
from services                import fred_service     as fred
from services                import data_service     as data
from services                import awesome_service  as fx_svc
from utils                   import fmt_currency_usd, fmt_currency_brl, fmt_points

TRIED = ["yfinance", "stooq"]

inject_css()
render_sidebar()
page_header("Global", "Ações americanas, ETFs e curva de juros dos EUA")

EQUITIES = {
    "S&P 500": "^GSPC",
    "QQQ":     "QQQ",
    "TSLA":    "TSLA",
    "NVDA":    "NVDA",
    "META":    "META",
    "GOOG":    "GOOG",
    "AAPL":    "AAPL",
    "TMF":     "TMF",
    "TLT":     "TLT",
    "PBR":     "PBR",
}

with st.spinner("Carregando mercados globais..."):
    quotes    = data.quotes(list(EQUITIES.values()))
    tr_curve  = fred.get_treasury_curve()
    fed_funds = fred.get_fed_funds()
    us_unemp  = fred.get_us_unemployment()
    spread    = fred.get_spread_10_2()
    hist_us10 = fred.get_treasury_history("DGS10", years=2)


def _fmt_value(ticker):
    q = quotes.get(ticker, {})
    if q.get("error") or q.get("price") is None:
        return None
    p = q["price"]
    return fmt_points(p) + " pts" if ticker.startswith("^") else fmt_currency_usd(p)

# Cotacao USD/BRL p/ equivalente em reais (opcional via sidebar)
_fx      = fx_svc.get_fx(["USD-BRL"]).get("USD-BRL", {})
_usd_brl = _fx.get("mid") or _fx.get("bid")
_show_brl = bool(st.session_state.get("show_brl_equiv")) and _usd_brl

def _brl_equiv(usd_value):
    if not _show_brl or usd_value is None:
        return None
    return fmt_currency_brl(usd_value * _usd_brl)

def _card(col, label, ticker, hint="", tooltip=""):
    with col:
        val = _fmt_value(ticker)
        q   = quotes.get(ticker, {})
        if val is None:
            error_card(label, tried=TRIED)
        else:
            # indice (^XXX) em pontos nao converte; acoes em USD sim
            sub = None if ticker.startswith("^") else _brl_equiv(q.get("price"))
            metric_card(label, val, q.get("change_pct"),
                        hint=hint, tooltip=tooltip, subvalue=sub)


# ── Row 1 ─────────────────────────────────────────────────────────────────────
_sources = sorted({q.get("source") for q in quotes.values() if q.get("source") and q.get("source") != "none"})
_age = format_age(max((q.get("fetched_at") or 0) for q in quotes.values()))
section_header("Índices & Ações", "Cotações em tempo real (delay 15 min)",
               timestamp=_age, source=" · ".join(_sources) if _sources else None)
cols = st.columns(5)
for col, (label, ticker, hint, tooltip) in zip(cols, [
    ("S&P 500", "^GSPC", "500 maiores empresas EUA",       "Índice de referência do mercado americano"),
    ("QQQ",     "QQQ",   "ETF Nasdaq-100",                 "ETF que replica as 100 maiores do Nasdaq"),
    ("TSLA",    "TSLA",  "Tesla — EV / Energia",           "Tesla Inc. — montadora e energia"),
    ("NVDA",    "NVDA",  "Nvidia — Chips / IA",            "Nvidia — líder em chips de IA"),
    ("META",    "META",  "Meta — Redes Sociais",           "Meta — Facebook, Instagram, WhatsApp"),
]):
    _card(col, label, ticker, hint, tooltip)

st.markdown("<br>", unsafe_allow_html=True)
cols2 = st.columns(5)
for col, (label, ticker, hint, tooltip) in zip(cols2, [
    ("GOOG", "GOOG", "Alphabet — Google / Cloud",   "Alphabet — Google Search, YouTube, Cloud"),
    ("AAPL", "AAPL", "Apple — Hardware / Software", "Apple Inc. — iPhone, Mac, serviços"),
    ("TMF",  "TMF",  "ETF Treasury 3x Long",        "Direxion Daily 20+ Year Treasury Bull 3X"),
    ("TLT",  "TLT",  "ETF Treasury 20+ anos",       "iShares 20+ Year Treasury Bond ETF"),
    ("PBR",  "PBR",  "Petrobras — ADR (NYSE)",      "Petrobras listada na NYSE em dólares"),
]):
    _card(col, label, ticker, hint, tooltip)

st.markdown("---")


# ── Treasuries ────────────────────────────────────────────────────────────────
section_header("Curva de Juros — EUA", "Treasuries por prazo (% a.a.)")
col_curve, col_macro = st.columns([3, 2])

with col_curve:
    if not tr_curve.empty:
        fig = yield_curve_chart(tr_curve, title="US Treasury Yield Curve", height=300)
        st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})

        # st.metric é nativo e funciona em colunas aninhadas sem unsafe_allow_html
        LABELS = {"2 anos": "US02y", "10 anos": "US10y",
                  "20 anos": "US20y", "30 anos": "US30y"}
        row = st.columns(4)
        for col, (mat, label) in zip(row, LABELS.items()):
            match = tr_curve[tr_curve["maturidade"] == mat]
            val   = float(match["yield_pct"].iloc[0]) if not match.empty else None
            with col:
                st.metric(label=label, value=f"{val:.2f}%" if val else "—",
                          help=f"Rendimento do Tesouro Americano — {mat}")
    else:
        st.warning("Curva de juros indisponível.")

with col_macro:
    section_header("Macro EUA", "")

    def _macro(label, val, unit, tooltip=""):
        if val is not None:
            st.markdown(f"""
            <div class="metric-card" style="margin-bottom:0.6rem;" title="{tooltip}">
                <div class="card-label">{label}</div>
                <div class="card-value" style="font-size:1.3rem;">
                    {val:.2f}<span style="font-size:0.8rem;color:#888;margin-left:4px;">{unit}</span>
                </div>
            </div>""", unsafe_allow_html=True)
        else:
            error_card(label)

    _macro("Fed Funds Rate",  fed_funds["value"], "% a.a.",
           "Taxa de juros básica americana definida pelo Federal Reserve")
    _macro("Desemprego EUA",  us_unemp["value"],  "%",
           "Taxa de desemprego americana")
    _macro("Spread 10y - 2y", spread["value"],    "p.p.",
           "Diferença entre juros de 10 e 2 anos — negativo indica inversão da curva")

# ── US10y histórico ───────────────────────────────────────────────────────────
if not hist_us10.empty:
    st.markdown("---")
    section_header("Juro Americano 10 anos — Histórico", "Últimos 2 anos")
    fig = line_chart(hist_us10, x_col="data", y_col="yield_pct",
                     title="US Treasury 10y (%)", y_label="% a.a.",
                     color="#4A90D9", fill=False, height=240)
    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})


# ── Detalhe por ticker ────────────────────────────────────────────────────────
render_detail(EQUITIES, currency="USD", period_default="6mo")

render_footer()
