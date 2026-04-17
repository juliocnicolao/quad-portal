import streamlit as st
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

st.set_page_config(page_title="Notícias | QUAD", page_icon="📰",
                   layout="wide", initial_sidebar_state="expanded")

from components.layout       import inject_css, render_sidebar, render_footer, page_header
from components.cards        import section_header
from components.news_ticker  import render_news_ticker
from services                import news_service as news

inject_css()
render_sidebar()
page_header("Notícias — Live Feed",
            "Agregador em tempo real · Valor, InfoMoney, G1, BBC, CNBC, Reuters e mais")

# ── Controles ────────────────────────────────────────────────────────────────
ctrl_c1, ctrl_c2, ctrl_c3 = st.columns([2, 2, 3])
with ctrl_c1:
    region = st.radio("Região:", ["Todas", "🇧🇷 Brasil", "🌎 Global"],
                      horizontal=True, label_visibility="collapsed")
with ctrl_c2:
    limit = st.select_slider("Qtd. itens:", options=[20, 40, 60, 100], value=40)
with ctrl_c3:
    if st.button("🔄 Atualizar agora"):
        news.get_news.clear()
        news._fetch_feed.clear()
        st.rerun()

region_key = {"Todas": "ALL", "🇧🇷 Brasil": "BR", "🌎 Global": "WORLD"}[region]

with st.spinner("Buscando notícias..."):
    items = news.get_news(region=region_key, limit=limit)
    items = news.refresh_age_strings(items)

if not items:
    st.warning("Não foi possível buscar notícias. Verifique sua conexão ou tente novamente.")
    render_footer()
    st.stop()

# ── Top headlines (hero) ─────────────────────────────────────────────────────
section_header("Manchetes", f"{len(items)} notícias — mais recentes primeiro")

# Grid 3-colunas com as top 6
top = items[:6]
cols = st.columns(3)
for i, it in enumerate(top):
    with cols[i % 3]:
        st.markdown(f"""
        <a href="{it['link']}" target="_blank" rel="noopener" style="text-decoration:none;">
          <div style="background:#141414;border:1px solid #1e1e1e;border-left:3px solid {it['color']};
                      border-radius:8px;padding:0.9rem 1rem;margin-bottom:0.8rem;
                      transition:background 0.15s;min-height:120px;">
            <div style="display:flex;gap:8px;align-items:center;margin-bottom:0.5rem;
                        font-family:ui-monospace,Consolas,monospace;">
              <span style="background:{it['color']};color:#fff;font-size:0.58rem;
                           font-weight:800;letter-spacing:0.08em;padding:2px 7px;
                           border-radius:2px;text-transform:uppercase;">{it['source']}</span>
              <span style="color:#555;font-size:0.6rem;">{it.get('age','')}</span>
            </div>
            <div style="color:#F0F0F0;font-size:0.9rem;line-height:1.35;font-weight:500;">
              {it['title']}
            </div>
          </div>
        </a>
        """, unsafe_allow_html=True)

st.markdown("---")

# ── Ticker completo + agrupamento por fonte ──────────────────────────────────
left, right = st.columns([2, 1])

with left:
    section_header("Todos os Feeds", "Lista completa ordenada por data")
    render_news_ticker(items, title="TODAS AS NOTÍCIAS", show_count=True)

with right:
    section_header("Por Fonte", "Agrupado por veículo")
    sources = {}
    for it in items:
        sources.setdefault(it["source"], []).append(it)
    for src, lst in sources.items():
        with st.expander(f"{src} ({len(lst)})", expanded=False):
            for it in lst[:10]:
                st.markdown(
                    f'<div style="padding:0.35rem 0;border-bottom:1px solid #181818;">'
                    f'<a href="{it["link"]}" target="_blank" style="color:#E0E0E0;'
                    f'text-decoration:none;font-size:0.82rem;line-height:1.3;">{it["title"]}</a>'
                    f'<div style="color:#555;font-size:0.6rem;margin-top:2px;">{it.get("age","")}</div>'
                    f'</div>',
                    unsafe_allow_html=True,
                )

render_footer()
