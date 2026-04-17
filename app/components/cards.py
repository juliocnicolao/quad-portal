"""Reusable metric cards — all HTML on single lines to avoid markdown parser issues."""

import streamlit as st
from utils import fmt_pct

_C_POS = "#26a269"
_C_NEG = "#C8232B"

_CARD  = "background:#1A1A1A;border:1px solid #2a2a2a;border-radius:8px;padding:1rem 1.2rem;text-align:left;height:100%;"
_LABEL = "font-size:0.7rem;color:#888;text-transform:uppercase;letter-spacing:0.1em;margin-bottom:0.25rem;"
_VALUE = "font-size:1.5rem;font-weight:700;color:#F0F0F0;line-height:1.1;"
_DELTA = "font-size:0.85rem;font-weight:600;"
_HINT  = "font-size:0.65rem;color:#555;margin-top:0.3rem;"


def metric_card(
    label: str,
    value: str,
    change_pct: float | None = None,
    hint: str | None = None,
    tooltip: str | None = None,
):
    color      = _C_POS if (change_pct or 0) >= 0 else _C_NEG
    delta_part = f'<span style="{_DELTA}color:{color};">{fmt_pct(change_pct)}</span>' if change_pct is not None else ""
    hint_part  = f'<div style="{_HINT}">{hint}</div>' if hint else ""
    tip        = f' title="{tooltip}"' if tooltip else ""

    # Single-line HTML — prevents markdown from breaking the block into paragraphs
    html = (f'<div style="{_CARD}"{tip}>'
            f'<div style="{_LABEL}">{label}</div>'
            f'<div style="{_VALUE}">{value}</div>'
            f'{delta_part}{hint_part}'
            f'</div>')
    st.markdown(html, unsafe_allow_html=True)


def metric_card_row(items: list[dict], cols: int = 4):
    columns = st.columns(cols)
    for i, item in enumerate(items):
        with columns[i % cols]:
            metric_card(
                label=item.get("label", ""),
                value=item.get("value", "—"),
                change_pct=item.get("change_pct"),
                hint=item.get("hint"),
                tooltip=item.get("tooltip"),
            )


def error_card(label: str, msg: str = "Dado indisponível",
               tried: list[str] | None = None):
    """Card padronizado para falha. `tried` lista as fontes testadas."""
    footer = ""
    if tried:
        footer = (f'<div style="font-size:0.6rem;color:#444;margin-top:0.35rem;">'
                  f'Fontes testadas: {" · ".join(tried)}</div>')
    html = (f'<div style="{_CARD}opacity:0.55;border-color:#3a1f1f;">'
            f'<div style="{_LABEL}">{label}</div>'
            f'<div style="font-size:1rem;color:#888;">⚠ indisponível</div>'
            f'<div style="{_HINT}">{msg}</div>'
            f'{footer}'
            f'</div>')
    st.markdown(html, unsafe_allow_html=True)


def freshness_badge(source: str | None, fetched_at: float | None = None) -> str:
    """HTML pequeno mostrando a fonte e há quanto tempo o dado foi obtido."""
    import time as _t
    if not source or source == "none":
        return ('<span style="font-size:0.6rem;color:#C8232B;'
                'background:#2a1818;padding:2px 6px;border-radius:4px;">offline</span>')
    age = ""
    if fetched_at:
        mins = max(0, int((_t.time() - fetched_at) / 60))
        age  = f" · há {mins}min" if mins else " · agora"
    return (f'<span style="font-size:0.6rem;color:#888;'
            f'background:#1f1f1f;padding:2px 6px;border-radius:4px;">'
            f'{source}{age}</span>')


def section_header(title: str, subtitle: str | None = None):
    sub = f'<div style="font-size:0.8rem;color:#666;margin-top:0.2rem;">{subtitle}</div>' if subtitle else ""
    html = (f'<div style="margin:1.5rem 0 0.75rem 0;">'
            f'<div style="font-size:1rem;font-weight:700;color:#F0F0F0;'
            f'border-left:3px solid #C8232B;padding-left:0.6rem;">{title}</div>'
            f'{sub}</div>')
    st.markdown(html, unsafe_allow_html=True)
