"""
Ticker detail panel — rendered inside a st.expander.
Fetches fresh data on demand (no automatic cache bypass needed;
user triggers by expanding / changing selection).
"""

import streamlit as st
from components.charts import candlestick_chart, line_chart
from services import data_service as data
from utils import fmt_currency_usd, fmt_currency_brl, fmt_pct


def render_detail(
    label_map: dict[str, str],
    currency: str = "USD",
    period_default: str = "6mo",
):
    """
    Renders a selectbox + expander with candlestick + key stats for any ticker.

    label_map: {display_name: yfinance_ticker}
    currency:  "USD" or "BRL"
    """
    st.markdown("---")
    with st.expander("🔍 Analisar ativo em detalhe", expanded=False):
        col_sel, col_per = st.columns([3, 1])
        with col_sel:
            selected_label = st.selectbox(
                "Selecione o ativo:", list(label_map.keys()), key=f"detail_{currency}"
            )
        with col_per:
            period = st.selectbox(
                "Período:", ["1mo", "3mo", "6mo", "1y", "2y"],
                index=["1mo", "3mo", "6mo", "1y", "2y"].index(period_default),
                key=f"period_{currency}",
            )

        ticker = label_map[selected_label]

        with st.spinner(f"Carregando {selected_label}..."):
            detail = data.detail(ticker)
            hist   = data.history(ticker, period=period)

        if detail.get("error") or hist.empty:
            st.warning(
                f"Dados indisponíveis para **{selected_label}** no momento. "
                f"Fontes testadas: yfinance · stooq."
            )
            return

        # ── Stats row ─────────────────────────────────────────────────────────
        fmt = fmt_currency_brl if currency == "BRL" else fmt_currency_usd

        s1, s2, s3, s4, s5 = st.columns(5)
        price      = detail.get("price")
        change_pct = detail.get("change_pct", 0)
        arrow      = "▲" if change_pct >= 0 else "▼"
        color_css  = "color:#26a269" if change_pct >= 0 else "color:#C8232B"

        with s1:
            st.markdown(f"""
            <div style="background:#1A1A1A;border:1px solid #2a2a2a;border-radius:8px;
                        padding:0.8rem 1rem;">
                <div style="font-size:0.65rem;color:#888;text-transform:uppercase;
                            letter-spacing:0.1em;">{selected_label}</div>
                <div style="font-size:1.4rem;font-weight:700;color:#F0F0F0;">
                    {fmt(price) if price else "—"}
                </div>
                <div style="font-size:0.85rem;font-weight:600;{color_css}">
                    {arrow} {change_pct:+.2f}%
                </div>
            </div>""", unsafe_allow_html=True)

        def _stat(col, label, val):
            with col:
                st.markdown(f"""
                <div style="background:#1A1A1A;border:1px solid #2a2a2a;border-radius:8px;
                            padding:0.8rem 1rem;">
                    <div style="font-size:0.65rem;color:#888;text-transform:uppercase;
                                letter-spacing:0.1em;">{label}</div>
                    <div style="font-size:1rem;font-weight:600;color:#F0F0F0;">{val}</div>
                </div>""", unsafe_allow_html=True)

        h52  = detail.get("high_52w")
        l52  = detail.get("low_52w")
        vol  = detail.get("volume")
        mcap = detail.get("market_cap")

        _stat(s2, "Máx. 52 semanas", fmt(h52) if h52 else "—")
        _stat(s3, "Mín. 52 semanas", fmt(l52) if l52 else "—")
        _stat(s4, "Vol. médio 3m",
              f"{vol/1_000_000:.1f}M" if vol and vol >= 1e6 else
              f"{vol/1_000:.0f}K" if vol else "—")
        _stat(s5, "Market Cap",
              f"$ {mcap/1e12:.2f}T" if mcap and mcap >= 1e12 else
              f"$ {mcap/1e9:.1f}B" if mcap and mcap >= 1e9 else "—")

        st.markdown("<br>", unsafe_allow_html=True)

        # ── Candlestick ───────────────────────────────────────────────────────
        if not hist.empty and all(c in hist.columns for c in ["Open","High","Low","Close"]):
            fig = candlestick_chart(hist, title=f"{selected_label} — {period}", height=360)
            st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
        elif not hist.empty and "Close" in hist.columns:
            df = hist.reset_index()
            date_col = "Date" if "Date" in df.columns else df.columns[0]
            fig = line_chart(df, x_col=date_col, y_col="Close",
                             title=f"{selected_label} — {period}",
                             y_label=currency, height=320)
            st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
