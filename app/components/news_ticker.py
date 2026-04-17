"""News ticker component — renderiza lista vertical de notícias estilo LIVE TICKER."""

import streamlit as st


_TICKER_CSS = """
<style>
.news-ticker-wrap {
    background:#0F0F0F; border:1px solid #1f1f1f; border-radius:10px;
    padding:0.9rem 0.8rem 0.6rem; max-height:720px; overflow-y:auto;
}
.news-ticker-wrap::-webkit-scrollbar { width:6px; }
.news-ticker-wrap::-webkit-scrollbar-track { background:#141414; }
.news-ticker-wrap::-webkit-scrollbar-thumb { background:#2a2a2a; border-radius:3px; }

.news-ticker-head {
    display:flex; justify-content:space-between; align-items:center;
    border-bottom:1px solid #1f1f1f; padding:0 0.1rem 0.55rem;
    margin-bottom:0.5rem;
    font-family: ui-monospace, "SF Mono", Consolas, monospace;
}
.news-ticker-head .lbl {
    color:#888; font-size:0.62rem; letter-spacing:0.18em; font-weight:700;
}
.news-ticker-head .lbl .dot {
    display:inline-block; width:6px; height:6px; background:#C8232B;
    border-radius:50%; margin-right:5px; animation:pulse 1.8s infinite;
}
.news-ticker-head .count {
    color:#2ec27e; font-size:0.62rem; letter-spacing:0.12em;
    border:1px solid #2ec27e; border-radius:3px; padding:1px 6px;
    font-weight:700;
}
@keyframes pulse { 0%,100%{opacity:1;} 50%{opacity:0.3;} }

.news-item {
    padding:0.55rem 0.35rem 0.55rem;
    border-bottom:1px solid #161616;
    transition:background 0.15s;
}
.news-item:last-child { border-bottom:none; }
.news-item:hover { background:#151515; }

.news-meta {
    display:flex; align-items:center; gap:6px; margin-bottom:0.3rem;
    font-family: ui-monospace, "SF Mono", Consolas, monospace;
}
.news-tag {
    font-size:0.55rem; font-weight:800; letter-spacing:0.08em;
    padding:1px 6px; border-radius:2px; text-transform:uppercase;
    color:#fff; flex-shrink:0;
}
.news-age { color:#555; font-size:0.6rem; letter-spacing:0.04em; }

.news-title {
    font-size:0.82rem; color:#E8E8E8; line-height:1.3;
    text-decoration:none; display:block;
    font-weight:500;
}
.news-title:hover { color:#C8232B; }
.news-title-link { text-decoration:none; }

.news-empty { color:#555; text-align:center; padding:2rem 0; font-size:0.8rem; }
</style>
"""


def render_news_ticker(items: list[dict], title: str = "LIVE NEWS TICKER",
                       show_count: bool = True):
    """Renderiza coluna de notícias."""
    st.markdown(_TICKER_CSS, unsafe_allow_html=True)

    count_html = (f'<span class="count">{len(items)} ITENS</span>'
                  if show_count else "")
    rows = ""
    if not items:
        rows = '<div class="news-empty">Sem notícias disponíveis no momento.</div>'
    else:
        for it in items:
            tag_style = f'background:{it.get("color", "#444")};'
            link = it.get("link") or "#"
            rows += (
                '<div class="news-item">'
                '<div class="news-meta">'
                f'<span class="news-tag" style="{tag_style}">{it["source"]}</span>'
                f'<span class="news-age">{it.get("age", "")}</span>'
                '</div>'
                f'<a class="news-title-link" href="{link}" target="_blank" rel="noopener">'
                f'<span class="news-title">{it["title"]}</span>'
                '</a>'
                '</div>'
            )

    html = (
        '<div class="news-ticker-wrap">'
        '<div class="news-ticker-head">'
        f'<span class="lbl"><span class="dot"></span>{title}</span>'
        f'{count_html}'
        '</div>'
        f'{rows}'
        '</div>'
    )
    st.markdown(html, unsafe_allow_html=True)
