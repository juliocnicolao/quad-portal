"""News service — agrega feeds RSS de finanças/economia BR e globais."""

from __future__ import annotations

import time
import datetime as _dt
from typing import Literal

import streamlit as st
import feedparser

from utils import CACHE_TTL
from utils.logger import get_logger

_log = get_logger(__name__)

# ── Feeds curados ────────────────────────────────────────────────────────────
# Cada feed: (label, url, lang, region, tag_color)
FEEDS = {
    # 🇧🇷 BR
    "Valor":        ("Valor Econômico",        "https://pox.globo.com/rss/valor/brasil", "pt", "BR", "#C8232B"),
    "Valor Int":    ("Valor Internacional",    "https://pox.globo.com/rss/valor/mundo",  "pt", "BR", "#C8232B"),
    "G1":           ("G1 Economia",            "https://g1.globo.com/rss/g1/economia/",   "pt", "BR", "#ED1C24"),
    "InfoMoney":    ("InfoMoney",              "https://www.infomoney.com.br/feed/",      "pt", "BR", "#00A859"),
    "Folha":        ("Folha Mercado",          "https://feeds.folha.uol.com.br/mercado/rss091.xml", "pt", "BR", "#FFB200"),
    "MoneyTimes":   ("Money Times",            "https://www.moneytimes.com.br/feed/",     "pt", "BR", "#0F4C81"),
    # 🌎 Global
    "BBC":          ("BBC Business",           "https://feeds.bbci.co.uk/news/business/rss.xml", "en", "WORLD", "#BB1919"),
    "CNBC":         ("CNBC Markets",           "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=10000664", "en", "WORLD", "#005594"),
    "Yahoo":        ("Yahoo Finance",          "https://finance.yahoo.com/news/rssindex", "en", "WORLD", "#6001D2"),
    "Reuters":      ("Reuters Business",       "https://www.reutersagency.com/feed/?best-topics=business-finance&post_type=best", "en", "WORLD", "#FF8000"),
    "MarketWatch":  ("MarketWatch",            "https://feeds.content.dowjones.io/public/rss/mw_topstories", "en", "WORLD", "#18A1B0"),
}


def _parse_entry_time(entry) -> float:
    """Extrai timestamp (epoch) de uma entry feedparser."""
    for attr in ("published_parsed", "updated_parsed"):
        t = getattr(entry, attr, None) or entry.get(attr) if hasattr(entry, "get") else None
        if t:
            try:
                return time.mktime(t)
            except Exception:
                pass
    return 0.0


def _fmt_age(ts: float) -> str:
    if ts <= 0:
        return ""
    delta = time.time() - ts
    if delta < 60:
        return "agora"
    if delta < 3600:
        return f"há {int(delta/60)}min"
    if delta < 86400:
        return f"há {int(delta/3600)}h"
    return f"há {int(delta/86400)}d"


@st.cache_data(ttl=300, persist="disk")   # 5 min
def _fetch_feed(url: str, limit: int = 15) -> list[dict]:
    """Busca um feed RSS individual. Retorna lista normalizada."""
    try:
        parsed = feedparser.parse(url)
        entries = parsed.entries[:limit] if parsed.entries else []
        out = []
        for e in entries:
            title = (e.get("title") or "").strip()
            if not title:
                continue
            out.append({
                "title":    title,
                "link":     e.get("link", ""),
                "summary":  (e.get("summary", "") or "")[:300],
                "ts":       _parse_entry_time(e),
            })
        return out
    except Exception as ex:
        _log.warning("Feed falhou %s: %s", url, ex)
        return []


@st.cache_data(ttl=300, persist="disk")   # 5 min
def get_news(
    region: Literal["ALL", "BR", "WORLD"] = "ALL",
    limit: int = 40,
    per_feed: int = 8,
) -> list[dict]:
    """
    Agrega todos os feeds, filtra por região, dedup por título, ordena por data desc.
    Retorna até `limit` itens.
    """
    all_items: list[dict] = []
    for key, (label, url, lang, reg, color) in FEEDS.items():
        if region != "ALL" and reg != region:
            continue
        items = _fetch_feed(url, limit=per_feed)
        for it in items:
            all_items.append({
                **it,
                "source":       label,
                "source_key":   key,
                "lang":         lang,
                "region":       reg,
                "color":        color,
                "age":          _fmt_age(it["ts"]),
            })

    # Dedup por título normalizado
    seen = set()
    unique = []
    for it in all_items:
        key = it["title"].lower().strip()[:80]
        if key in seen:
            continue
        seen.add(key)
        unique.append(it)

    # Ordena por timestamp desc (mais recente primeiro)
    unique.sort(key=lambda x: x["ts"], reverse=True)
    return unique[:limit]


def refresh_age_strings(items: list[dict]) -> list[dict]:
    """Recalcula a string 'há Xmin' sem invalidar cache das entradas."""
    for it in items:
        it["age"] = _fmt_age(it["ts"])
    return items
