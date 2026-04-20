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

/* ── Section header com timestamp ───────────────────────────────────────── */
.section-header-row {
    display:flex; justify-content:space-between; align-items:flex-end;
    margin:1.5rem 0 0.75rem 0; gap:0.75rem; flex-wrap:wrap;
}
.section-header-title {
    font-size:1rem; font-weight:700; color:#F0F0F0;
    border-left:3px solid #C8232B; padding-left:0.6rem;
}
.section-header-sub { font-size:0.8rem; color:#666; margin-top:0.2rem; }
.section-timestamp {
    font-size:0.6rem; color:#888; background:#1f1f1f;
    padding:3px 8px; border-radius:4px; letter-spacing:0.05em;
    white-space:nowrap;
}

/* ── Mobile breakpoints ─────────────────────────────────────────────────── */
@media (max-width: 768px) {
    .block-container { padding-left:0.6rem !important; padding-right:0.6rem !important; }
    .page-title { font-size:1.25rem !important; }
    .page-subtitle { font-size:0.75rem !important; }
    .metric-card { padding:0.7rem 0.85rem !important; }
    .metric-card .card-value { font-size:1.15rem !important; }
    .fx-table { font-size:0.78rem; }
    .fx-table th, .fx-table td { padding:0.35rem 0.45rem; }
    .section-header-row { flex-direction:column; align-items:flex-start; }
    [data-testid="stSidebar"] { min-width:240px; }
}
@media (max-width: 480px) {
    .metric-card .card-value { font-size:1rem !important; }
    .section-header-title { font-size:0.9rem !important; }
}

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

from components.cards  import metric_card, section_header, error_card, freshness_badge, format_age
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
    st.page_link("pages/6_Watchlist.py",      label="Watchlist",    icon="⭐")
    st.markdown("---")
    st.markdown("**Preferências**")
    st.session_state["show_brl_equiv"] = st.toggle(
        "Mostrar equivalente em BRL",
        value=st.session_state.get("show_brl_equiv", False),
        help="Adiciona o valor convertido em reais abaixo de preços em USD.",
    )
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
    fx_data = fx_svc.get_fx([
        "USD-BRL", "EUR-BRL", "GBP-BRL", "CHF-BRL", "JPY-BRL",
        "CAD-BRL", "AUD-BRL", "CNY-BRL", "ARS-BRL",
        "USD-PYG", "USD-UYU",
    ])
    # Cross-rates BRL → vizinhos (AwesomeAPI não tem BRL-PYG/UYU direto)
    _usd_brl_mid = (fx_data.get("USD-BRL") or {}).get("mid")
    if _usd_brl_mid:
        for src_pair, dst_pair in [("USD-PYG", "BRL-PYG"), ("USD-UYU", "BRL-UYU")]:
            src = fx_data.get(src_pair) or {}
            if not src.get("error") and src.get("mid"):
                fx_data[dst_pair] = {
                    "bid":        src["mid"] / _usd_brl_mid,
                    "mid":        src["mid"] / _usd_brl_mid,
                    "change_pct": (src.get("change_pct", 0) or 0) - ((fx_data["USD-BRL"].get("change_pct") or 0)),
                    "error":      False,
                }
    # Fallback yfinance para pares que falharam no AwesomeAPI
    YF_FX_FALLBACK = {
        "EUR-BRL": "EURBRL=X", "GBP-BRL": "GBPBRL=X",
        "CHF-BRL": "CHFBRL=X", "JPY-BRL": "JPYBRL=X",
        "CAD-BRL": "CADBRL=X", "AUD-BRL": "AUDBRL=X",
        "CNY-BRL": "CNYBRL=X", "ARS-BRL": "ARSBRL=X",
        "USD-PYG": "USDPYG=X", "USD-UYU": "USDUYU=X",
    }
    for pair, yf_tkr in YF_FX_FALLBACK.items():
        d = fx_data.get(pair) or {}
        if d.get("error") or not d.get("mid"):
            q = data.quote(yf_tkr)
            if q.get("price"):
                fx_data[pair] = {
                    "bid":        q["price"],
                    "mid":        q["price"],
                    "change_pct": q.get("change_pct"),
                    "error":      False,
                }
    # Recomputar cross-rates se preenchemos agora por yfinance
    if _usd_brl_mid:
        for src_pair, dst_pair in [("USD-PYG", "BRL-PYG"), ("USD-UYU", "BRL-UYU")]:
            src = fx_data.get(src_pair) or {}
            if not src.get("error") and src.get("mid") and not (fx_data.get(dst_pair) or {}).get("mid"):
                fx_data[dst_pair] = {
                    "bid":        src["mid"] / _usd_brl_mid,
                    "mid":        src["mid"] / _usd_brl_mid,
                    "change_pct": (src.get("change_pct", 0) or 0) - ((fx_data["USD-BRL"].get("change_pct") or 0)),
                    "error":      False,
                }
    # BRL-ARS = 1 / ARS-BRL (inversão direta)
    _ars = fx_data.get("ARS-BRL") or {}
    if not _ars.get("error") and _ars.get("mid") and _ars["mid"] > 0:
        fx_data["BRL-ARS"] = {
            "bid":        1 / _ars["mid"],
            "mid":        1 / _ars["mid"],
            "change_pct": -(_ars.get("change_pct") or 0),
            "error":      False,
        }
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
_mkt_sources = {q.get("source") for q in [ibov, sp500, btc, wti, ouro] if q.get("source")}
_mkt_src = " · ".join(sorted(_mkt_sources)) if _mkt_sources else None
_mkt_age = format_age(max((q.get("fetched_at") or 0) for q in [ibov, sp500, btc, wti, ouro]))
section_header("Mercados", "Principais índices e ativos",
               timestamp=_mkt_age, source=_mkt_src)
c1, c2, c3, c4, c5, c6 = st.columns(6)

def _card(col, label, value, change_pct, hint=None, tooltip=None, subvalue=None):
    with col:
        if value is None:
            error_card(label, tried=TRIED)
        else:
            metric_card(label, value, change_pct, hint, tooltip, subvalue=subvalue)


# Cotacao USD/BRL p/ conversao de equivalente em reais
_usd_brl = fx_data.get("USD-BRL", {}).get("mid") or fx_data.get("USD-BRL", {}).get("bid")
_show_brl = bool(st.session_state.get("show_brl_equiv")) and _usd_brl

def _brl_equiv(usd_value: float | None) -> str | None:
    if not _show_brl or usd_value is None:
        return None
    return fmt_currency_brl(usd_value * _usd_brl)

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
      tooltip="Preço do Bitcoin em dólares americanos",
      subvalue=_brl_equiv(btc.get("price")))

_card(c6, "Petróleo WTI",
      fmt_currency_usd(wti["price"]) if wti["price"] else None,
      wti.get("change_pct"),
      hint="Futuro WTI",
      tooltip="Contrato futuro de petróleo West Texas Intermediate",
      subvalue=_brl_equiv(wti.get("price")))


st.markdown("<br>", unsafe_allow_html=True)


# ── Row 2: Mini charts ────────────────────────────────────────────────────────
_hist_src = ibov_hist.attrs.get("source") if hasattr(ibov_hist, "attrs") else None
section_header("Evolução Recente", "Últimos 6 meses", source=_hist_src)
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

    # (pair, label, flag, unit_prefix, decimals)
    FX_LABELS = [
        ("USD-BRL", "Dólar Americano",    "🇺🇸", "R$",  4),
        ("EUR-BRL", "Euro",               "🇪🇺", "R$",  4),
        ("GBP-BRL", "Libra Esterlina",    "🇬🇧", "R$",  4),
        ("CHF-BRL", "Franco Suíço",       "🇨🇭", "R$",  4),
        ("JPY-BRL", "Iene Japonês",       "🇯🇵", "R$",  4),
        ("CAD-BRL", "Dólar Canadense",    "🇨🇦", "R$",  4),
        ("AUD-BRL", "Dólar Australiano",  "🇦🇺", "R$",  4),
        ("CNY-BRL", "Yuan Chinês",        "🇨🇳", "R$",  4),
        ("ARS-BRL", "Peso Argentino",     "🇦🇷", "R$",  4),
        ("BRL-ARS", "Real → Peso ARG",    "🇧🇷→🇦🇷", "$", 2),
        ("BRL-PYG", "Real → Guarani PY",  "🇧🇷→🇵🇾", "₲", 2),
        ("BRL-UYU", "Real → Peso URU",    "🇧🇷→🇺🇾", "$U", 2),
    ]

    rows_html = ""
    for pair, name, flag, unit, dec in FX_LABELS:
        d = fx_data.get(pair, {})
        if d.get("error") or not d.get("mid"):
            continue
        mid   = f"{unit} {d['mid']:,.{dec}f}"
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


# ── Row 4: Notícias ───────────────────────────────────────────────────────────
try:
    from services                import news_service as news_svc
    from components.news_ticker  import render_news_ticker
    section_header("Live News", "Manchetes de economia e mercados — agregador BR + Global")

    # Auto-refresh server-side a cada 2min (dispara rerun mesmo com aba em background).
    # Cai pra JS legado se o pacote nao estiver instalado.
    _ar_status = "desligado"
    _news_auto = bool(st.session_state.get("news_autorefresh_home", True))
    if _news_auto:
        try:
            from streamlit_autorefresh import st_autorefresh
            st_autorefresh(interval=120_000, key="news_autorefresh_tick")
            _ar_status = "ligado (2min · server-side)"
        except Exception:
            st.markdown(
                '<script>setTimeout(function(){'
                'var u=new URL(window.location.href);'
                'u.searchParams.set("nref","1");'
                'window.location.href=u.toString();}, 120000);</script>',
                unsafe_allow_html=True,
            )
            if st.query_params.get("nref") == "1":
                try:
                    news_svc.get_news.clear()
                    news_svc._fetch_feed.clear()
                except Exception:
                    pass
            _ar_status = "ligado (2min · fallback JS)"

    # Botao de refresh manual — invalida cache e rerun
    _btn_col, _spacer = st.columns([1, 6])
    with _btn_col:
        if st.button("🔄 Atualizar agora", key="news_refresh_btn",
                     help="Força re-fetch dos feeds ignorando o cache"):
            try:
                news_svc.get_news.clear()
                news_svc._fetch_feed.clear()
            except Exception:
                pass
            st.rerun()

    n_left, n_right = st.columns(2)
    import datetime as _dt
    _fetch_ts = _dt.datetime.now().strftime("%H:%M:%S")
    with st.spinner("Buscando notícias..."):
        br_news    = news_svc.get_news(region="BR",    limit=12)
        world_news = news_svc.get_news(region="WORLD", limit=12)
        br_news    = news_svc.refresh_age_strings(br_news)
        world_news = news_svc.refresh_age_strings(world_news)
    with n_left:
        render_news_ticker(br_news,    title="🇧🇷 BRASIL LIVE",  show_count=True)
    with n_right:
        render_news_ticker(world_news, title="🌎 GLOBAL LIVE",  show_count=True)
    st.markdown(
        '<div style="display:flex;justify-content:space-between;align-items:center;'
        'margin-top:0.4rem;font-size:0.72rem;">'
        f'<span style="color:#555;">⟳ Auto-refresh {_ar_status} · última renderização {_fetch_ts}</span>'
        '<a href="/Noticias" target="_self" style="color:#888;text-decoration:none;">'
        'Ver todas as notícias →</a></div>',
        unsafe_allow_html=True,
    )
except Exception as _news_err:
    st.caption(f"Notícias temporariamente indisponíveis: {_news_err}")


# ── Footer ────────────────────────────────────────────────────────────────────
st.markdown("""
<div class="portal-footer">
    Dados com atraso de até 15 minutos — não utilize para decisões de trading. &nbsp;|&nbsp;
    QUAD Wealth Management © 2024
</div>
""", unsafe_allow_html=True)
