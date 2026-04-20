import streamlit as st
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

st.set_page_config(page_title="Brasil | QUAD", page_icon="🌎",
                   layout="wide", initial_sidebar_state="expanded")

from components.layout      import inject_css, render_sidebar, render_footer, page_header
from components.cards       import section_header, metric_card, error_card, format_age
from components.charts      import line_chart, bar_movers
from components.detail_panel import render_detail
from services               import brapi_service as brapi
from services               import yfinance_service as yf_svc
from services               import stooq_service    as stooq
from services               import bcb_service as bcb
from services               import data_service as data
from utils                  import fmt_points, fmt_pct

TRIED_BR = ["brapi", "yfinance", "stooq"]
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

@st.cache_data(ttl=600, persist="disk")
def _get_br_quotes_cascade(tickers: list[str]) -> dict:
    """Cascata brapi (PETRE4) -> yfinance (PETR4.SA) -> stooq (PETR4.SA)."""
    # 1) Bulk brapi primeiro (mais rapido se funcionar)
    try:
        bulk = brapi.get_quotes(tickers)
    except Exception:
        bulk = {}

    out = {}
    for t in tickers:
        q = bulk.get(t) if bulk else None
        if q and not q.get("error") and q.get("change_pct") is not None:
            out[t] = q
            continue
        # Fallback: yfinance / stooq com sufixo .SA
        q2 = yf_svc.get_quote(t + ".SA")
        if not q2.get("error") and q2.get("change_pct") is not None:
            out[t] = q2
            continue
        q3 = stooq.get_quote(t + ".SA")
        if not q3.get("error") and q3.get("change_pct") is not None:
            out[t] = q3
            continue
        out[t] = {"ticker": t, "price": None, "change_pct": None, "error": True}
    return out


with st.spinner("Carregando dados do Brasil..."):
    ibov      = data.quote("^BVSP", br=True)
    ibov_hist = data.history("^BVSP", period="1y")
    ipca_hist = bcb.get_ipca_history(n=24)
    # quotes agora vem do fragment live (Top Movers / Liquidez)


# ── Ibovespa hero ─────────────────────────────────────────────────────────────
section_header("Ibovespa", "Índice da Bolsa de Valores do Brasil — B3",
               timestamp=format_age(ibov.get("fetched_at")),
               source=ibov.get("source"))
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
        error_card("Ibovespa", tried=TRIED_BR)

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


# ── Top Movers + Top Ativos Liquidez (live fragment) ──────────────────────────
# Fragment unico que renderiza as duas secoes que dependem de quotes intraday.
# Re-executa a cada 60s sem reload da pagina. O cache dos quotes e invalidado
# a cada tick pra garantir dados frescos.

LIQUID = ["PETR4","VALE3","ITUB4","BBDC4","BBAS3",
          "B3SA3","ELET3","WEGE3","ABEV3","SUZB3"]

@st.cache_data(ttl=900, persist="disk")
def _get_volume(tickers):
    """Usa data.history (yfinance->stooq) para calcular preco atual e volume
    medio de 3 meses. Estavel no Streamlit Cloud (fast_info e bloqueado)."""
    rows = []
    for t in tickers:
        try:
            df = data.history(t + ".SA", period="3mo")
            if df.empty or "Close" not in df.columns:
                rows.append({"Ativo": t, "_price": 0, "_vol": 0})
                continue
            closes = df["Close"].dropna()
            vols   = df["Volume"].dropna() if "Volume" in df.columns else None
            price  = float(closes.iloc[-1]) if len(closes) else 0
            if vols is not None and len(vols):
                avg_vol = float(vols.mean())
                avg_px  = float(closes.tail(len(vols)).mean())
                fin_vol = avg_vol * avg_px
            else:
                fin_vol = 0
            rows.append({"Ativo": t, "_price": price, "_vol": fin_vol})
        except Exception:
            rows.append({"Ativo": t, "_price": 0, "_vol": 0})
    return rows


@st.fragment(run_every=60)
def _render_live_quotes_block():
    import datetime as _dt
    # Invalida cache de quotes a cada tick (volume de 3m fica cacheado normal)
    try:
        _get_br_quotes_cascade.clear()
    except Exception:
        pass

    quotes = _get_br_quotes_cascade(TICKERS)
    _fetch_ts = _dt.datetime.now().strftime("%H:%M:%S")

    # ── Top Movers ───────────────────────────────────────────────────────────
    section_header("Top Movers", "Maiores altas e baixas do dia")

    valid = [
        {**q, "ticker": t}
        for t, q in quotes.items()
        if not q.get("error") and q.get("change_pct") is not None
    ]

    if valid:
        df_movers = pd.DataFrame(valid).sort_values("change_pct", ascending=False)
        top5_up   = df_movers[df_movers["change_pct"] > 0].head(5)
        top5_down = df_movers[df_movers["change_pct"] < 0].sort_values("change_pct").head(5)

        max_abs = float(df_movers["change_pct"].abs().max())
        pad     = max(max_abs * 0.15, 0.5)
        x_up    = [0, max_abs + pad]
        x_down  = [-(max_abs + pad), 0]

        col_up, col_down = st.columns(2)
        with col_up:
            if top5_up.empty:
                st.info("Nenhum ativo em alta no momento.")
            else:
                fig = bar_movers(top5_up, "ticker", "change_pct", "▲ Maiores Altas", 240)
                fig.update_xaxes(range=x_up)
                st.plotly_chart(fig, use_container_width=True,
                                config={"displayModeBar": False})
        with col_down:
            if top5_down.empty:
                st.info("Nenhum ativo em baixa no momento.")
            else:
                fig = bar_movers(top5_down, "ticker", "change_pct", "▼ Maiores Baixas", 240)
                fig.update_xaxes(range=x_down)
                st.plotly_chart(fig, use_container_width=True,
                                config={"displayModeBar": False})
    else:
        st.warning(
            "Top Movers temporariamente indisponível — todas as fontes "
            "(brapi · yfinance · stooq) falharam para os tickers acompanhados."
        )

    st.markdown("---")

    # ── Top Ativos por Liquidez ──────────────────────────────────────────────
    section_header("Top Ativos — Liquidez", "Volume financeiro médio (3 meses)")

    rows = _get_volume(LIQUID)
    df_liq = pd.DataFrame(rows).sort_values("_vol", ascending=False)
    df_liq["Preço"]         = df_liq["_price"].map(
        lambda v: f"R$ {v:.2f}" if v else "—")
    df_liq["Vol. Médio 3m"] = df_liq["_vol"].map(
        lambda v: f"R$ {v/1e9:.2f}B" if v >= 1e9
        else f"R$ {v/1e6:.0f}M" if v >= 1e6
        else f"R$ {v/1e3:.0f}K" if v else "—")
    df_liq["Var. Dia"] = df_liq["Ativo"].map(
        lambda t: fmt_pct(quotes[t]["change_pct"])
        if t in quotes and not quotes[t].get("error")
        and quotes[t].get("change_pct") is not None else "—")

    st.dataframe(df_liq[["Ativo","Preço","Var. Dia","Vol. Médio 3m"]],
                 use_container_width=True, hide_index=True)

    # Countdown visivel
    st.markdown(
        f"""
        <div style="margin-top:0.4rem;font-size:0.72rem;color:#777;">
          ⟳ Auto-refresh ligado (60s · fragment) · último fetch {_fetch_ts}
          <span id="br-live-countdown" style="color:#0a9;margin-left:0.5rem;"></span>
        </div>
        <script>
        (function(){{
          var startMs = Date.now();
          var duration = 60000;
          function tick(){{
            var el = document.getElementById('br-live-countdown');
            if (!el) return;
            var rem = Math.max(0, duration - (Date.now() - startMs));
            var m = Math.floor(rem/60000);
            var s = Math.floor((rem%60000)/1000);
            el.textContent = '· próxima em ' + m + ':' + (s<10?'0':'') + s;
          }}
          tick();
          if (window._brLiveCountdownIv) clearInterval(window._brLiveCountdownIv);
          window._brLiveCountdownIv = setInterval(tick, 1000);
        }})();
        </script>
        """,
        unsafe_allow_html=True,
    )

st.markdown("---")


# Chama o fragment live (Top Movers + Top Ativos - Liquidez)
_render_live_quotes_block()


# ── Renda Fixa BR ────────────────────────────────────────────────────────────
st.markdown("---")
from services import renda_fixa_service as rf

section_header("Renda Fixa", "Tesouro Direto e curva DI (proxy via futuros)")

col_td, col_di = st.columns([3, 2])

with col_td:
    with st.spinner("Carregando Tesouro Direto..."):
        td = rf.get_tesouro_direto()
    if td.empty:
        st.warning("Tesouro Direto indisponível no momento.")
    else:
        st.caption(f"Atualizado em {td['Data Base'].max().strftime('%d/%m/%Y')} · "
                   f"Fonte: Tesouro Transparente")
        # colunas úteis
        show = td[[
            "Tipo Titulo", "Data Vencimento",
            "Taxa Compra Manha", "Taxa Venda Manha",
            "PU Compra Manha", "PU Venda Manha",
        ]].copy()
        show["Data Vencimento"] = show["Data Vencimento"].dt.strftime("%d/%m/%Y")
        show.rename(columns={
            "Tipo Titulo": "Título",
            "Taxa Compra Manha": "Taxa Compra %",
            "Taxa Venda Manha":  "Taxa Venda %",
            "PU Compra Manha":   "PU Compra",
            "PU Venda Manha":    "PU Venda",
        }, inplace=True)
        for c in ["Taxa Compra %", "Taxa Venda %"]:
            show[c] = show[c].map(lambda v: f"{v:.2f}%" if pd.notna(v) else "—")
        for c in ["PU Compra", "PU Venda"]:
            show[c] = show[c].map(lambda v: f"R$ {v:,.2f}".replace(",","X").replace(".",",").replace("X",".") if pd.notna(v) else "—")
        st.dataframe(show, use_container_width=True, hide_index=True, height=360)

with col_di:
    with st.spinner("Calculando curva DI..."):
        di = rf.get_di_curve()
    if di.empty:
        st.warning("Curva DI indisponível.")
    else:
        import plotly.graph_objects as go
        fig = go.Figure(go.Scatter(
            x=di["vencimento"], y=di["taxa"],
            mode="lines+markers",
            line=dict(color="#C8232B", width=2),
            marker=dict(size=10, color="#C8232B"),
            text=[f"{t:.2f}%" for t in di["taxa"]],
            textposition="top center",
            hovertemplate="%{x}<br><b>%{y:.2f}%</b><extra>DI</extra>",
        ))
        fig.update_layout(
            paper_bgcolor="#0D0D0D", plot_bgcolor="#1A1A1A",
            font=dict(color="#F0F0F0", size=11),
            margin=dict(l=10, r=10, t=35, b=10),
            xaxis=dict(gridcolor="#2a2a2a"),
            yaxis=dict(gridcolor="#2a2a2a", ticksuffix="%"),
            height=340,
            title=dict(text="Curva DI — projeção implícita (% a.a.)",
                       font=dict(size=13, color="#888")),
        )
        st.plotly_chart(fig, use_container_width=True,
                        config={"displayModeBar": False})
        st.caption("Proxy via DI1 futures (Yahoo/Stooq). "
                   "Aproximação visual — não use para precificação.")


# ── Detalhe por ticker ────────────────────────────────────────────────────────
BR_DETAIL = {t: t + ".SA" for t in TICKERS}
BR_DETAIL["Ibovespa"] = "^BVSP"
render_detail(BR_DETAIL, currency="BRL", period_default="6mo")

render_footer()
