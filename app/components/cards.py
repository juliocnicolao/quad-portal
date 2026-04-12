"""Reusable metric cards — all HTML on single lines to avoid markdown parser issues."""

import streamlit as st
from app.utils import fmt_pct

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


def error_card(label: str, msg: str = "Dado indisponível"):
    html = (f'<div style="{_CARD}opacity:0.4;">'
            f'<div style="{_LABEL}">{label}</div>'
            f'<div style="font-size:1rem;color:#666;">—</div>'
            f'<div style="{_HINT}">{msg}</div>'
            f'</div>')
    st.markdown(html, unsafe_allow_html=True)


def section_header(title: str, subtitle: str | None = None):
    sub = f'<div style="font-size:0.8rem;color:#666;margin-top:0.2rem;">{subtitle}</div>' if subtitle else ""
    html = (f'<div style="margin:1.5rem 0 0.75rem 0;">'
            f'<div style="font-size:1rem;font-weight:700;color:#F0F0F0;'
            f'border-left:3px solid #C8232B;padding-left:0.6rem;">{title}</div>'
            f'{sub}</div>')
    st.markdown(html, unsafe_allow_html=True)
