"""CEPEA/B3 — Brazilian agricultural reference prices in BRL.

Fonte: noticiasagricolas.com.br (agregador de cotacoes Cepea/Esalq).
A pagina renderiza HTML server-side com tabelas `cot-fisicas`. Para cada
indicador procuramos o titulo `<h2>` correspondente e a primeira linha da
tabela seguinte (data, valor, variacao %).

Indicadores escolhidos sao os de referencia nacional (Cepea/Esalq, usados
inclusive como subjacente dos contratos futuros da B3):
  - Soja:      Indicador da Soja ESALQ/B3 - Paranagua  (R$/saca 60kg)
  - Milho:     Indicador do Milho Esalq/B3            (R$/saca 60kg, Campinas)
  - Boi Gordo: Indicador do Boi Gordo Esalq / B3      (R$/arroba 15kg)
  - Trigo:     Preco Medio do Trigo Cepea/Esalq       (R$/saca 60kg, PR)

Atualizacao: diaria (D-1) — Cepea publica em horario comercial nos dias uteis.
"""
from __future__ import annotations

import re
import streamlit as st

from utils import CACHE_TTL
from utils.http import get_text
from utils.logger import get_logger

_log = get_logger(__name__)

# Codigo -> (url da pagina, titulo do h2 a procurar, unidade legivel)
INDICATORS: dict[str, dict] = {
    "soja": {
        "url":      "https://www.noticiasagricolas.com.br/cotacoes/soja",
        "title":    "Indicador da Soja ESALQ/B3 - Paranagu",  # final acentuado removido
        "unit":     "R$/saca 60kg",
        "label":    "Soja (R$/saca)",
        "tooltip":  "Indicador ESALQ/B3 Paranagua — referencia nacional para soja, "
                    "subjacente do contrato futuro de soja na B3.",
    },
    "milho": {
        "url":      "https://www.noticiasagricolas.com.br/cotacoes/milho",
        "title":    "Indicador do Milho Esalq/B3",
        "unit":     "R$/saca 60kg",
        "label":    "Milho (R$/saca)",
        "tooltip":  "Indicador ESALQ/B3 Campinas — referencia nacional para milho, "
                    "subjacente do contrato futuro de milho na B3.",
    },
    "boi": {
        "url":      "https://www.noticiasagricolas.com.br/cotacoes/boi",
        "title":    "Indicador do Boi Gordo Esalq / B3",
        "unit":     "R$/arroba",
        "label":    "Boi Gordo (R$/@)",
        "tooltip":  "Indicador ESALQ/B3 do Boi Gordo (arroba de 15kg) — "
                    "subjacente do contrato futuro de boi gordo na B3.",
    },
    "trigo": {
        "url":      "https://www.noticiasagricolas.com.br/cotacoes/trigo",
        # a pagina serve UTF-8 mas com chars acentuados quebrados (replacement
        # chars). Buscamos por substring sem acento que sobrevive ao parse.
        "title":    "Trigo Cepea/Esalq",
        "title_alt": "Preco Medio do Trigo Cepea/Esalq",
        # tabela tem 4 colunas (Data/Regiao/R$/t/Var%). Filtramos linha do PR
        # e convertemos tonelada -> saca de 60kg multiplicando por 0.06.
        "row_filter": "Paran",       # casa "Parana"/"Paran�" (encoding quebrado)
        "scale":      0.06,           # R$/t -> R$/saca 60kg
        "unit":       "R$/saca 60kg",
        "label":      "Trigo (R$/saca)",
        "tooltip":   "Preco medio do Trigo Cepea/Esalq (Parana) — convertido "
                     "de R$/tonelada para R$/saca de 60kg (x 0,06).",
    },
}

_NUM_RE = re.compile(r"-?\d+(?:\.\d+)?(?:,\d+)?")


def _to_float(s: str) -> float | None:
    """'127,74' -> 127.74; '+0,66' -> 0.66; '1.234,56' -> 1234.56"""
    if s is None:
        return None
    s = s.strip().replace("+", "")
    m = _NUM_RE.search(s)
    if not m:
        return None
    raw = m.group(0)
    # se tem virgula, decimal eh virgula; pontos sao milhar
    if "," in raw:
        raw = raw.replace(".", "").replace(",", ".")
    try:
        return float(raw)
    except ValueError:
        return None


def _extract_first_row(html: str, title_substrs: list[str],
                       row_filter: str | None = None) -> dict | None:
    """Busca o primeiro h2 cujo titulo contenha algum dos substrings,
    e extrai a primeira linha (ou a que casa `row_filter`) da proxima
    <table class='cot-fisicas'>.

    Suporta tabelas de 3 colunas (data/valor/var) e de 4 colunas
    (data/regiao/valor/var). No 4-col, valor eh a coluna 3, var a coluna 4.

    Retorna {'date': 'DD/MM/YYYY', 'price': float, 'change_pct': float} ou None.
    """
    idx = -1
    for sub in title_substrs:
        if not sub:
            continue
        idx = html.find(sub)
        if idx >= 0:
            break
    if idx < 0:
        return None

    snippet = html[idx: idx + 6000]
    # Localiza inicio do tbody
    tb = re.search(r"<tbody[^>]*>", snippet, re.IGNORECASE)
    if not tb:
        return None
    body = snippet[tb.end():]
    # Termina no </tbody>
    end = body.lower().find("</tbody>")
    if end >= 0:
        body = body[:end]

    # Quebra em linhas
    rows = re.findall(r"<tr[^>]*>(.*?)</tr>", body, re.IGNORECASE | re.DOTALL)
    if not rows:
        return None

    def _parse_row(row_html: str) -> tuple[list[str], dict | None]:
        cells = re.findall(r"<td[^>]*>(.*?)</td>", row_html,
                           re.IGNORECASE | re.DOTALL)
        cells = [re.sub(r"<[^>]+>", "", c).strip() for c in cells]
        if len(cells) < 3:
            return cells, None
        if len(cells) >= 4:
            # data, regiao, valor, var
            d, _, v, ch = cells[0], cells[1], cells[2], cells[3]
        else:
            d, v, ch = cells[0], cells[1], cells[2]
        price = _to_float(v)
        if price is None:
            return cells, None
        return cells, {
            "date":       d,
            "price":      price,
            "change_pct": _to_float(ch),
        }

    # Se ha filtro, procura a linha que casa; se nao, primeira linha valida
    for row_html in rows:
        cells, parsed = _parse_row(row_html)
        if parsed is None:
            continue
        if row_filter:
            joined = " | ".join(cells)
            if row_filter.lower() not in joined.lower():
                continue
        return parsed
    return None


@st.cache_data(ttl=CACHE_TTL)
def get_brl_quotes(codes: list[str] | None = None) -> dict[str, dict]:
    """Retorna {code: {price, change_pct, date, unit, label, tooltip, error}}.

    `codes` opcional — default: todos em INDICATORS.
    Nao levanta excecoes — em caso de falha, marca `error: True`.
    """
    if codes is None:
        codes = list(INDICATORS.keys())

    out: dict[str, dict] = {}
    # Cache local de paginas ja baixadas (evita refetch se 2 indicadores
    # virem da mesma URL — nao eh o caso hoje, mas barato e robusto).
    page_cache: dict[str, str | None] = {}

    for code in codes:
        cfg = INDICATORS.get(code)
        if not cfg:
            out[code] = {"error": True, "reason": "unknown code"}
            continue

        url = cfg["url"]
        if url not in page_cache:
            try:
                page_cache[url] = get_text(
                    url,
                    timeout=15,
                    retries=1,
                    headers={
                        "User-Agent": (
                            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                            "AppleWebKit/537.36 (KHTML, like Gecko) "
                            "Chrome/131.0.0.0 Safari/537.36"
                        ),
                        "Accept-Language": "pt-BR,pt;q=0.9",
                    },
                )
            except Exception as ex:
                _log.warning("cepea fetch %s: %s", url, ex)
                page_cache[url] = None

        html = page_cache[url]
        if not html:
            out[code] = {
                "error": True, "label": cfg["label"], "unit": cfg["unit"],
                "tooltip": cfg["tooltip"], "reason": "fetch failed",
            }
            continue

        titles = [cfg["title"]]
        if cfg.get("title_alt"):
            titles.append(cfg["title_alt"])
        row = _extract_first_row(html, titles, row_filter=cfg.get("row_filter"))
        if not row:
            _log.warning("cepea: nao encontrou linha pra %s", code)
            out[code] = {
                "error": True, "label": cfg["label"], "unit": cfg["unit"],
                "tooltip": cfg["tooltip"], "reason": "parse failed",
            }
            continue

        scale = cfg.get("scale")
        price = row["price"] * scale if scale else row["price"]
        out[code] = {
            "error":      False,
            "price":      price,
            "change_pct": row["change_pct"],   # var % nao escala
            "date":       row["date"],
            "label":      cfg["label"],
            "unit":       cfg["unit"],
            "tooltip":    cfg["tooltip"],
        }

    return out


if __name__ == "__main__":
    import json
    print(json.dumps(get_brl_quotes(), indent=2, ensure_ascii=False, default=str))
