import streamlit as st
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

st.set_page_config(page_title="Watchlist & Comparador | QUAD", page_icon="⭐",
                   layout="wide", initial_sidebar_state="expanded")

from components.layout import inject_css, render_sidebar, render_footer, page_header
from components.cards  import section_header, metric_card, error_card, format_age
from components.charts import multi_line_chart, line_chart
from services          import data_service as data
from utils             import fmt_currency_usd, fmt_currency_brl, fmt_points
import pandas as pd

inject_css()
render_sidebar()
page_header("Watchlist & Comparador",
            "Monte sua carteira de acompanhamento e compare ativos normalizados (base 100)")


# ── Catálogo de tickers conhecidos ───────────────────────────────────────────
CATALOG = {
    # Índices
    "Ibovespa":      "^BVSP",
    "S&P 500":       "^GSPC",
    "Nasdaq":        "^IXIC",
    "Dow Jones":     "^DJI",
    "FTSE 100":      "^FTSE",
    "DAX":           "^GDAXI",
    "Nikkei":        "^N225",
    # Ações BR
    "PETR4":         "PETR4.SA",
    "VALE3":         "VALE3.SA",
    "ITUB4":         "ITUB4.SA",
    "BBAS3":         "BBAS3.SA",
    "WEGE3":         "WEGE3.SA",
    # Ações US
    "AAPL":          "AAPL",
    "MSFT":          "MSFT",
    "GOOG":          "GOOG",
    "TSLA":          "TSLA",
    "NVDA":          "NVDA",
    "META":          "META",
    # Commodities
    "Petróleo Brent":"BZ=F",
    "Ouro":          "GC=F",
    "Prata":         "SI=F",
    # Cripto
    "Bitcoin":       "BTC-USD",
    "Ethereum":      "ETH-USD",
    # FX
    "USD/BRL":       "USDBRL=X",
}

# Reverse map p/ display
TICKER_TO_LABEL = {v: k for k, v in CATALOG.items()}


# ── Session state ────────────────────────────────────────────────────────────
if "watchlist" not in st.session_state:
    # default: alguns do caixa do cliente
    st.session_state["watchlist"] = ["^BVSP", "USDBRL=X", "^GSPC", "BTC-USD", "GC=F"]


# ── URL query params para persistência simples ─────────────────────────────
qp = st.query_params
if "wl" in qp and qp["wl"]:
    try:
        url_wl = [t.strip() for t in qp["wl"].split(",") if t.strip()]
        if url_wl and url_wl != st.session_state["watchlist"]:
            st.session_state["watchlist"] = url_wl
    except Exception:
        pass


def _sync_url():
    st.query_params["wl"] = ",".join(st.session_state["watchlist"])


# ── Gestão da watchlist ──────────────────────────────────────────────────────
section_header("Sua Watchlist",
               "Ativos selecionados ficam salvos na sessão. "
               "Compartilhe o link — a lista viaja com ele.")

col_add, col_manage = st.columns([3, 2])

with col_add:
    # Permite escolher do catálogo OU digitar ticker livre
    mode = st.radio("Adicionar por:", ["Catálogo", "Ticker livre"],
                    horizontal=True, label_visibility="collapsed")
    if mode == "Catálogo":
        opts = [k for k, v in CATALOG.items() if v not in st.session_state["watchlist"]]
        sel  = st.selectbox("Escolha um ativo:", opts or ["(todos já adicionados)"],
                            disabled=not opts, key="cat_sel")
        if st.button("➕ Adicionar", disabled=not opts):
            st.session_state["watchlist"].append(CATALOG[sel])
            _sync_url()
            st.rerun()
    else:
        raw = st.text_input("Ticker (ex.: MGLU3.SA, AMZN, DOGE-USD):", key="free_ticker")
        if st.button("➕ Adicionar livre", disabled=not raw):
            t = raw.strip().upper()
            if t and t not in st.session_state["watchlist"]:
                st.session_state["watchlist"].append(t)
                _sync_url()
                st.rerun()

with col_manage:
    if st.session_state["watchlist"]:
        to_remove = st.multiselect(
            "Remover ativos:",
            options=st.session_state["watchlist"],
            format_func=lambda t: f"{TICKER_TO_LABEL.get(t, t)} ({t})",
        )
        c1, c2 = st.columns(2)
        with c1:
            if st.button("🗑 Remover selecionados", disabled=not to_remove):
                st.session_state["watchlist"] = [
                    t for t in st.session_state["watchlist"] if t not in to_remove
                ]
                _sync_url()
                st.rerun()
        with c2:
            if st.button("Limpar tudo"):
                st.session_state["watchlist"] = []
                _sync_url()
                st.rerun()


# ── Cards da watchlist ───────────────────────────────────────────────────────
wl = st.session_state["watchlist"]
if not wl:
    st.info("Sua watchlist está vazia. Adicione ativos acima para começar.")
    render_footer()
    st.stop()

with st.spinner("Atualizando watchlist..."):
    quotes = {t: data.quote(t) for t in wl}

cols = st.columns(min(len(wl), 5))
for i, t in enumerate(wl):
    q = quotes[t]
    label = TICKER_TO_LABEL.get(t, t)
    with cols[i % len(cols)]:
        if q.get("error") or q.get("price") is None:
            error_card(label, tried=["yfinance", "stooq"])
        else:
            price = q["price"]
            # heurística simples de formatação
            if t.startswith("^"):
                val = fmt_points(price) + " pts"
            elif t in ("USDBRL=X", "EURBRL=X") or ".SA" in t or t == "USDBRL=X":
                val = fmt_currency_brl(price) if ".SA" in t or "BRL" in t else fmt_currency_usd(price)
            else:
                val = fmt_currency_usd(price)
            metric_card(label, val, q.get("change_pct"), hint=t)


st.markdown("---")


# ── Comparador (gráfico normalizado) ─────────────────────────────────────────
section_header("Comparador — performance relativa",
               "Todos os ativos rebalanceados para 100 no início do período escolhido")

comp_c1, comp_c2 = st.columns([3, 1])
with comp_c1:
    picks = st.multiselect(
        "Selecione 2–6 ativos da watchlist:",
        options=wl,
        default=wl[:min(4, len(wl))],
        format_func=lambda t: f"{TICKER_TO_LABEL.get(t, t)} ({t})",
    )
with comp_c2:
    period = st.selectbox("Período:", ["1mo", "3mo", "6mo", "1y", "2y", "5y"],
                          index=3)

if len(picks) < 2:
    st.info("Selecione pelo menos 2 ativos para comparar.")
else:
    with st.spinner("Baixando históricos..."):
        series = []
        for t in picks:
            df = data.history(t, period=period)
            if df.empty or "Close" not in df.columns:
                continue
            closes = df["Close"].dropna()
            if closes.empty:
                continue
            base   = closes.iloc[0]
            norm   = (closes / base) * 100
            series.append({
                "name": TICKER_TO_LABEL.get(t, t),
                "x":    norm.index,
                "y":    norm.values,
            })

    if not series:
        st.warning("Não foi possível carregar o histórico de nenhum ativo selecionado.")
    else:
        fig = multi_line_chart(
            series,
            title=f"Performance relativa (base 100) — {period}",
            y_label="Índice (base 100)",
            height=420,
        )
        st.plotly_chart(fig, use_container_width=True,
                        config={"displayModeBar": False})

        # Tabela de retornos
        rows = []
        for s in series:
            last  = float(s["y"][-1])
            ret   = last - 100
            rows.append({
                "Ativo":      s["name"],
                "Índice":     f"{last:.2f}",
                "Retorno":    f"{ret:+.2f}%",
                "Max":        f"{max(s['y']):.2f}",
                "Min":        f"{min(s['y']):.2f}",
            })
        df_ret = pd.DataFrame(rows).sort_values("Retorno", ascending=False)
        st.dataframe(df_ret, use_container_width=True, hide_index=True)


# ── Exportar snapshot HTML ────────────────────────────────────────────────────
st.markdown("---")
section_header("Exportar", "Snapshot HTML da watchlist atual (abre em qualquer navegador)")

def _build_snapshot_html() -> str:
    import datetime as _dt
    rows_html = ""
    for t in wl:
        q = quotes[t]
        label = TICKER_TO_LABEL.get(t, t)
        if q.get("error") or q.get("price") is None:
            rows_html += (f'<tr><td>{label}</td><td>{t}</td>'
                          f'<td colspan="2" style="color:#C8232B;">indisponível</td></tr>')
            continue
        price = q["price"]
        pct   = q.get("change_pct") or 0
        css   = "pos" if pct >= 0 else "neg"
        arrow = "▲" if pct >= 0 else "▼"
        rows_html += (f'<tr><td>{label}</td><td>{t}</td>'
                      f'<td><b>{price:,.2f}</b></td>'
                      f'<td class="{css}">{arrow} {pct:+.2f}%</td></tr>')

    return f"""<!doctype html><html lang="pt-BR"><head>
<meta charset="utf-8"><title>QUAD Watchlist — Snapshot</title>
<style>
body{{font-family:system-ui,-apple-system,sans-serif;background:#0D0D0D;color:#F0F0F0;
     padding:2rem;max-width:900px;margin:auto;}}
h1{{color:#C8232B;font-size:1.4rem;margin:0;}}
.sub{{color:#888;font-size:0.85rem;margin-bottom:1.5rem;}}
table{{width:100%;border-collapse:collapse;font-size:0.9rem;}}
th,td{{padding:0.6rem 0.8rem;border-bottom:1px solid #2a2a2a;text-align:left;}}
th{{color:#888;font-size:0.7rem;text-transform:uppercase;letter-spacing:0.1em;}}
.pos{{color:#26a269;font-weight:600;}}
.neg{{color:#C8232B;font-weight:600;}}
.footer{{color:#444;font-size:0.7rem;margin-top:2rem;text-align:center;}}
@media print {{ body {{ background:white; color:black; }} .pos{{color:#070;}} .neg{{color:#C00;}} }}
</style></head><body>
<h1>QUAD Wealth — Watchlist Snapshot</h1>
<div class="sub">Gerado em {_dt.datetime.now().strftime("%d/%m/%Y %H:%M")}</div>
<table><thead><tr><th>Ativo</th><th>Ticker</th><th>Preço</th><th>Var. Dia</th></tr></thead>
<tbody>{rows_html}</tbody></table>
<div class="footer">Dados com atraso de até 15 minutos — não utilize para decisões de trading.</div>
</body></html>"""

st.download_button(
    "📄 Baixar snapshot HTML",
    data=_build_snapshot_html(),
    file_name=f"quad-watchlist-{pd.Timestamp.now():%Y%m%d-%H%M}.html",
    mime="text/html",
    help="Arquivo HTML auto-contido. Abre em qualquer navegador; imprime como PDF via Ctrl+P."
)

render_footer()
