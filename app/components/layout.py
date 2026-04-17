"""Shared layout helpers — sidebar, CSS injection."""

import streamlit as st

_CSS = """
<style>
/* Hide Streamlit's auto-generated page navigation (top of sidebar) */
[data-testid="stSidebarNav"] { display: none !important; }

/* Content area */
.block-container { padding-top: 2.5rem !important; padding-bottom: 3.5rem; }

/* Footer */
.portal-footer { position:fixed; bottom:0; left:0; right:0; background:#0D0D0D;
    border-top:1px solid #1f1f1f; text-align:center; padding:0.4rem;
    font-size:0.65rem; color:#444; z-index:999; }

hr { border-color:#2a2a2a; }

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
    /* Cards empilham com mais respiro */
    .block-container { padding-left:0.6rem !important; padding-right:0.6rem !important; }

    .page-title, div[style*="font-size:1.6rem"] { font-size:1.25rem !important; }
    .page-subtitle { font-size:0.75rem !important; }

    /* Metric cards mais compactos e com valor menor */
    .metric-card .card-value, div[style*="font-size:1.5rem;font-weight:700"] {
        font-size:1.15rem !important;
    }
    .metric-card { padding:0.7rem 0.85rem !important; }

    /* Tabelas roláveis horizontalmente em mobile */
    .fx-table { font-size:0.78rem; }
    .fx-table th, .fx-table td { padding:0.35rem 0.45rem; }

    /* Section header empilha em telas pequenas */
    .section-header-row { flex-direction:column; align-items:flex-start; }

    /* Sidebar fecha por padrao em mobile — Streamlit ja faz isso,
       aqui garantimos que o conteudo nao quebre */
    [data-testid="stSidebar"] { min-width:240px; }
}

@media (max-width: 480px) {
    /* Em telas muito pequenas, reduzir ainda mais */
    .metric-card .card-value, div[style*="font-size:1.5rem;font-weight:700"] {
        font-size:1rem !important;
    }
    .section-header-title { font-size:0.9rem !important; }
}
</style>
"""

_BRAND = (
    '<div style="text-align:center;padding:1rem 0 1.5rem 0;'
    'border-bottom:1px solid #2a2a2a;margin-bottom:1rem;">'
    '<div style="font-size:2rem;font-weight:900;color:#C8232B;letter-spacing:-0.02em;">Q</div>'
    '<div style="font-size:1.1rem;font-weight:700;color:#F0F0F0;'
    'letter-spacing:0.08em;text-transform:uppercase;">QUAD Wealth</div>'
    '<div style="font-size:0.7rem;color:#888;letter-spacing:0.12em;'
    'text-transform:uppercase;">Portal Global</div>'
    '</div>'
)


def inject_css():
    st.markdown(_CSS, unsafe_allow_html=True)


def render_sidebar():
    with st.sidebar:
        st.markdown(_BRAND, unsafe_allow_html=True)
        st.markdown("**Navegação**")
        st.page_link("main.py",                label="Visão Geral",  icon="📊")
        st.page_link("pages/1_Brasil.py",      label="Brasil",       icon="🌎")
        st.page_link("pages/2_Global.py",      label="Global",       icon="🌐")
        st.page_link("pages/3_Commodities.py", label="Commodities",  icon="📦")
        st.page_link("pages/4_Cripto.py",      label="Cripto",       icon="🪙")
        st.page_link("pages/5_Fundamentos.py", label="Fundamentos",  icon="🌍")
        st.markdown("---")
        st.markdown("**Preferências**")
        st.session_state["show_brl_equiv"] = st.toggle(
            "Mostrar equivalente em BRL",
            value=st.session_state.get("show_brl_equiv", False),
            help="Adiciona o valor convertido em reais abaixo de preços em USD.",
        )
        st.caption("Dados com atraso de até 15 min.")


def render_footer():
    st.markdown(
        '<div class="portal-footer">Dados com atraso de até 15 minutos — '
        'não utilize para decisões de trading. &nbsp;|&nbsp; '
        'QUAD Wealth Management © 2024</div>',
        unsafe_allow_html=True,
    )


def page_header(title: str, subtitle: str):
    st.markdown(
        f'<div style="font-size:1.6rem;font-weight:700;color:#F0F0F0;margin-bottom:0.1rem;">{title}</div>'
        f'<div style="font-size:0.8rem;color:#666;margin-bottom:1.5rem;">{subtitle}</div>',
        unsafe_allow_html=True,
    )
