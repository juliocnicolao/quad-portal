"""Utility helpers: formatters, cache config, constants."""

import streamlit as st

try:
    FRED_API_KEY = st.secrets["FRED_API_KEY"]
except Exception:
    FRED_API_KEY = "586d413968f0f9ad258273cb9c7aef8b"  # fallback local
CACHE_TTL    = 900  # 15 minutes in seconds

# Accent palette
COLOR_RED    = "#C8232B"
COLOR_GREEN  = "#26a269"
COLOR_BG     = "#0D0D0D"
COLOR_CARD   = "#1A1A1A"
COLOR_BORDER = "#2a2a2a"
COLOR_MUTED  = "#888888"


def fmt_currency_brl(value: float) -> str:
    """R$ 1.234,56"""
    return f"R$ {value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def fmt_currency_usd(value: float) -> str:
    """$ 1,234.56"""
    return f"$ {value:,.2f}"


def fmt_pct(value: float, decimals: int = 2) -> str:
    """▲ 1,23% or ▼ -1,23%"""
    arrow = "▲" if value >= 0 else "▼"
    return f"{arrow} {value:+.{decimals}f}%"


def fmt_points(value: float) -> str:
    """1.234,56 pts"""
    return f"{value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def delta_color(value: float) -> str:
    """Returns CSS class name based on sign."""
    return "card-delta-pos" if value >= 0 else "card-delta-neg"
