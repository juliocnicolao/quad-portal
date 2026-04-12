"""Reusable Plotly charts — line, yield curve, bar movers, candlestick."""

import plotly.graph_objects as go
import pandas as pd

# ── Theme constants ────────────────────────────────────────────────────────────
_BG      = "#0D0D0D"
_CARD_BG = "#1A1A1A"
_GRID    = "#2a2a2a"
_RED     = "#C8232B"
_GREEN   = "#26a269"
_TEXT    = "#F0F0F0"
_MUTED   = "#888888"

_BASE_LAYOUT = dict(
    paper_bgcolor=_BG,
    plot_bgcolor=_CARD_BG,
    font=dict(color=_TEXT, size=12),
    margin=dict(l=10, r=10, t=30, b=10),
    xaxis=dict(gridcolor=_GRID, showgrid=True, zeroline=False),
    yaxis=dict(gridcolor=_GRID, showgrid=True, zeroline=False),
    legend=dict(bgcolor="rgba(0,0,0,0)", font=dict(color=_MUTED, size=11)),
    hovermode="x unified",
)


def _hex_to_rgba(hex_color: str, alpha: float = 0.08) -> str:
    """Convert #RRGGBB to rgba(r,g,b,alpha) — compatible with Plotly 6."""
    h = hex_color.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return f"rgba({r},{g},{b},{alpha})"


def _tight_range(series: pd.Series, pad: float = 0.08):
    """Y-axis range with padding around data — avoids collapsing to zero baseline."""
    s = series.dropna()
    if s.empty:
        return None
    lo, hi = s.min(), s.max()
    margin = (hi - lo) * pad if (hi - lo) > 0 else abs(hi) * pad or 1
    return [lo - margin, hi + margin]


def line_chart(
    df: pd.DataFrame,
    x_col: str,
    y_col: str,
    title: str = "",
    y_label: str = "",
    color: str = _RED,
    fill: bool = True,
    height: int = 280,
) -> go.Figure:
    """Single-series area/line chart with tight y-axis range."""
    fillcolor = _hex_to_rgba(color) if color.startswith("#") else "rgba(200,35,43,0.08)"
    y_range   = _tight_range(df[y_col]) if fill else None

    fig = go.Figure()

    if fill:
        # Ghost base trace at data minimum — fills between ghost and data (not to zero)
        lo = df[y_col].dropna().min()
        fig.add_trace(go.Scatter(
            x=df[x_col], y=[lo] * len(df),
            mode="lines", line=dict(color="rgba(0,0,0,0)", width=0),
            showlegend=False, hoverinfo="skip",
        ))

    fig.add_trace(go.Scatter(
        x=df[x_col],
        y=df[y_col],
        mode="lines",
        line=dict(color=color, width=2),
        fill="tonexty" if fill else "none",
        fillcolor=fillcolor,
        name=y_label or y_col,
        hovertemplate=f"%{{y:,.2f}}<extra>{y_label or y_col}</extra>",
    ))

    yaxis_cfg = {**_BASE_LAYOUT["yaxis"], "title": y_label}
    if y_range:
        yaxis_cfg["range"] = y_range

    fig.update_layout(**{
        **_BASE_LAYOUT,
        "title":  dict(text=title, font=dict(size=13, color=_MUTED)),
        "yaxis":  yaxis_cfg,
        "height": height,
    })
    return fig


def yield_curve_chart(
    df: pd.DataFrame,
    maturity_col: str = "maturidade",
    yield_col: str = "yield_pct",
    title: str = "Curva de Juros",
    height: int = 300,
) -> go.Figure:
    """Yield curve — line + scatter markers."""
    df = df.dropna(subset=[yield_col])
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=df[maturity_col],
        y=df[yield_col],
        mode="lines+markers",
        line=dict(color=_RED, width=2.5),
        marker=dict(size=7, color=_RED, line=dict(color=_TEXT, width=1)),
        hovertemplate="%{x}: <b>%{y:.2f}%</b><extra></extra>",
        name="Yield",
    ))
    fig.update_layout(**{
        **_BASE_LAYOUT,
        "title":  dict(text=title, font=dict(size=13, color=_MUTED)),
        "yaxis":  {**_BASE_LAYOUT["yaxis"], "title": "% a.a."},
        "height": height,
    })
    return fig


def bar_movers(
    df: pd.DataFrame,
    label_col: str,
    value_col: str,
    title: str = "",
    height: int = 280,
) -> go.Figure:
    """Horizontal bar chart — green positive, red negative."""
    df = df.copy().sort_values(value_col)
    colors = [_GREEN if v >= 0 else _RED for v in df[value_col]]

    fig = go.Figure(go.Bar(
        x=df[value_col],
        y=df[label_col],
        orientation="h",
        marker_color=colors,
        text=df[value_col].map(lambda v: f"{v:+.2f}%"),
        textposition="outside",
        hovertemplate="%{y}: <b>%{x:+.2f}%</b><extra></extra>",
    ))
    fig.update_layout(**{
        **_BASE_LAYOUT,
        "title":  dict(text=title, font=dict(size=13, color=_MUTED)),
        "xaxis":  {**_BASE_LAYOUT["xaxis"], "title": "Variação %", "ticksuffix": "%"},
        "height": height,
    })
    return fig


def multi_line_chart(
    series: list[dict],
    title: str = "",
    y_label: str = "",
    height: int = 300,
) -> go.Figure:
    """Multi-series line chart with tight y-axis range."""
    colors = [_RED, "#4A90D9", "#F5A623", "#7ED321", "#9B59B6"]
    fig = go.Figure()
    all_y = []
    for i, s in enumerate(series):
        fig.add_trace(go.Scatter(
            x=s["x"], y=s["y"],
            mode="lines", name=s["name"],
            line=dict(color=s.get("color", colors[i % len(colors)]), width=2),
            hovertemplate=f"%{{y:,.2f}}<extra>{s['name']}</extra>",
        ))
        all_y.extend(list(s["y"]))
    import pandas as pd
    y_range = _tight_range(pd.Series(all_y))
    yaxis_cfg = {**_BASE_LAYOUT["yaxis"], "title": y_label}
    if y_range:
        yaxis_cfg["range"] = y_range
    fig.update_layout(**{
        **_BASE_LAYOUT,
        "title":  dict(text=title, font=dict(size=13, color=_MUTED)),
        "yaxis":  yaxis_cfg,
        "height": height,
    })
    return fig


def candlestick_chart(
    df: pd.DataFrame,
    title: str = "",
    height: int = 350,
) -> go.Figure:
    """Candlestick OHLC. df must have DatetimeIndex and Open/High/Low/Close columns."""
    fig = go.Figure(go.Candlestick(
        x=df.index,
        open=df["Open"],
        high=df["High"],
        low=df["Low"],
        close=df["Close"],
        increasing_line_color=_GREEN,
        decreasing_line_color=_RED,
        name="",
    ))
    fig.update_layout(**{
        **_BASE_LAYOUT,
        "title":  dict(text=title, font=dict(size=13, color=_MUTED)),
        "xaxis":  {**_BASE_LAYOUT["xaxis"], "rangeslider": {"visible": False}},
        "height": height,
    })
    return fig
