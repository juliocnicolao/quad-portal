"""Collector: calendario economico US + BR via investing.com.

Fonte: cada event page do investing.com tem `__NEXT_DATA__` SSR com
`state.economicCalendarEventStore.occurrences[]` — array de releases
passadas + upcoming, com forecast/actual/previous/occurrence_time.

Descoberta dos slugs: recon via endpoint
`endpoints.investing.com/.../events/occurrences` (sem auth) filtrado por
country_id. Ver `recon/investing_calendar_recon.py`. Slugs estabilizados
em `config.yaml` (calendar.events.US|BR).

Fluxo do collector:
    1. Le watchlist de eventos do config.yaml
    2. Para cada slug: httpx GET /economic-calendar/{slug}
    3. Extrai __NEXT_DATA__ via regex, parseia JSON
    4. Pega state.economicCalendarEventStore.event (metadata) + .occurrences
    5. Filtra occurrences pra janela [hoje - lookback_days, hoje + lookahead_days]
    6. Upsert em economic_events (UNIQUE(event_time, country, event_name))
    7. Sleep request_delay_s entre requests (gentil com o investing)

Retorna:
    {
      "status": "ok"|"partial"|"failed",
      "events_configured": int,
      "events_fetched": int,
      "events_failed": [{"slug": ..., "error": ...}, ...],
      "occurrences_upserted": int,
    }

`partial` = ao menos 1 slug funcionou E ao menos 1 falhou.
`failed`  = todos os slugs falharam (problema sistemico, ex: 403 do Cloudflare).
"""
from __future__ import annotations

import json
import logging
import re
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import yaml

from storage.db import get_conn

_log = logging.getLogger(__name__)

_REPO_ROOT   = Path(__file__).resolve().parent.parent
_CONFIG_PATH = _REPO_ROOT / "config.yaml"

# country_id -> codigo de 2 letras usado na nossa tabela
_COUNTRY_BY_CID = {5: "US", 32: "BR"}

_NEXT_DATA_RE = re.compile(
    r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>',
    re.S,
)


def _load_config() -> dict:
    cfg = yaml.safe_load(_CONFIG_PATH.read_text(encoding="utf-8"))
    return cfg.get("calendar", {})


def fetch_event_html(page, slug: str, timeout_ms: int = 30000) -> str:
    """Navega em Playwright page pra /economic-calendar/{slug} e retorna HTML.

    `page` eh um Playwright Page pre-configurado (ver CalendarBrowser).
    investing.com usa Cloudflare JS-challenge — espera ate __NEXT_DATA__
    aparecer no DOM (sinal de que o challenge resolveu).
    """
    url = f"https://www.investing.com/economic-calendar/{slug}"
    page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
    # aguarda ate o __NEXT_DATA__ carregar (pode demorar se CF challenge ativo)
    try:
        page.wait_for_selector('script#__NEXT_DATA__', timeout=timeout_ms,
                               state="attached")
    except Exception:
        # nao achou — pode ter caido em challenge persistente
        pass
    return page.content()


class CalendarBrowser:
    """Context manager que encapsula o ciclo do Playwright chromium.

    Uso:
        with CalendarBrowser(timeout=30) as cb:
            html = fetch_event_html(cb.page, "cpi-733")
            ...
    """
    def __init__(self, timeout: float = 30.0, headless: bool = True):
        self._timeout_ms = int(timeout * 1000)
        self._headless = headless
        self._p = None
        self._browser = None
        self._context = None
        self.page = None

    def __enter__(self):
        from playwright.sync_api import sync_playwright
        self._p = sync_playwright().start()
        self._browser = self._p.chromium.launch(
            headless=self._headless,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--disable-dev-shm-usage",
                "--no-sandbox",
            ],
        )
        self._context = self._browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/131.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1440, "height": 900},
            locale="en-US",
        )
        # mascara sinal `navigator.webdriver === true` (detector classico)
        self._context.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', { get: () => undefined });"
        )
        self.page = self._context.new_page()
        self.page.set_default_timeout(self._timeout_ms)
        # warm-up: visita calendar listing pra passar o challenge 1x
        try:
            self.page.goto("https://www.investing.com/economic-calendar/",
                           wait_until="domcontentloaded",
                           timeout=self._timeout_ms)
            # espera ate passar do challenge CF (__NEXT_DATA__ aparece so
            # no HTML "real"); se nao aparecer, continua mesmo assim
            try:
                self.page.wait_for_selector('script#__NEXT_DATA__',
                                            timeout=self._timeout_ms,
                                            state="attached")
            except Exception:
                pass
        except Exception as ex:
            _log.warning("warm-up falhou (seguindo mesmo assim): %s", ex)
        return self

    def __exit__(self, *exc_info):
        try:
            if self._browser:
                self._browser.close()
        finally:
            if self._p:
                self._p.stop()
        return False


def extract_next_data(html: str) -> dict:
    """Extrai e parseia o payload embutido no <script id=__NEXT_DATA__>."""
    m = _NEXT_DATA_RE.search(html)
    if not m:
        raise ValueError("__NEXT_DATA__ nao encontrado no HTML")
    return json.loads(m.group(1))


def parse_event_page(next_data: dict) -> tuple[dict, list[dict]]:
    """Isola (metadata, occurrences) do __NEXT_DATA__.

    Returns:
        metadata: {country_id, currency, importance, long_name, short_name,
                   event_id, category, event_cycle_suffix, source, page_link}
        occurrences: lista crua de occurrences conforme vem no payload
                     (mantem todos os campos — normalizacao em parse_occurrences)
    """
    try:
        store = next_data["props"]["pageProps"]["state"]["economicCalendarEventStore"]
    except (KeyError, TypeError) as ex:
        raise ValueError(f"estrutura __NEXT_DATA__ inesperada: {ex}")
    meta = store.get("event") or {}
    occ  = store.get("occurrences") or []
    if not isinstance(meta, dict) or not meta:
        raise ValueError("state.economicCalendarEventStore.event ausente ou vazio")
    if not isinstance(occ, list):
        raise ValueError("state.economicCalendarEventStore.occurrences nao eh lista")
    return meta, occ


def _parse_iso_z(s: str) -> datetime | None:
    """ISO8601 (com Z opcional) -> datetime aware UTC."""
    if not s or not isinstance(s, str):
        return None
    try:
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        return datetime.fromisoformat(s)
    except ValueError:
        return None


def parse_occurrences(
    metadata: dict,
    occurrences: list[dict],
    event_name: str,
    now_utc: datetime,
    lookback_days: int,
    lookahead_days: int,
) -> list[dict]:
    """Normaliza occurrences crus pra rows prontas pro DB.

    Filtra por janela temporal. Calcula surprise = actual - forecast e
    surprise_pct = surprise / |forecast|.
    """
    country = _COUNTRY_BY_CID.get(metadata.get("country_id"))
    if country is None:
        # evento fora de US/BR — vazio em vez de erro
        return []
    importance = metadata.get("importance") or "low"
    unit       = None           # pegamos do primeiro occurrence que tiver
    source     = metadata.get("source") or "investing.com"

    t_min = now_utc - timedelta(days=lookback_days)
    t_max = now_utc + timedelta(days=lookahead_days)

    rows: list[dict] = []
    for o in occurrences:
        t = _parse_iso_z(o.get("occurrence_time"))
        if t is None or t < t_min or t > t_max:
            continue

        actual   = o.get("actual")
        forecast = o.get("forecast")
        previous = o.get("previous")
        # surprise (apenas quando ambos existem)
        surprise = None
        surprise_pct = None
        if actual is not None and forecast is not None:
            try:
                surprise = float(actual) - float(forecast)
                if float(forecast) != 0:
                    surprise_pct = surprise / abs(float(forecast))
            except (TypeError, ValueError):
                surprise = None
                surprise_pct = None

        if unit is None and o.get("unit"):
            unit = o.get("unit")

        rows.append({
            "event_time": t.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "country":    country,
            "event_name": event_name,
            "impact":     importance,
            "forecast":   _to_float_or_none(forecast),
            "previous":   _to_float_or_none(previous),
            "actual":     _to_float_or_none(actual),
            "surprise":   surprise,
            "surprise_pct": surprise_pct,
            "unit":       o.get("unit") or unit,
            "source":     f"investing:{metadata.get('page_link','')}".strip(":"),
            "source_raw": json.dumps({
                "occurrence_id":       o.get("occurrence_id"),
                "reference_period":    o.get("reference_period"),
                "actual_to_forecast":  o.get("actual_to_forecast"),
                "revised_to_previous": o.get("revised_to_previous"),
                "preliminary":         o.get("preliminary"),
                "precision":           o.get("precision"),
            }, separators=(",", ":")),
        })
    return rows


def _to_float_or_none(x: Any) -> float | None:
    if x is None:
        return None
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def _upsert_rows(rows: list[dict], ts_collected: str) -> int:
    sql = """
        INSERT INTO economic_events
            (ts_collected, event_time, country, event_name, impact,
             forecast, previous, actual, surprise, surprise_pct,
             unit, source, source_raw)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(event_time, country, event_name) DO UPDATE SET
            ts_collected = excluded.ts_collected,
            impact       = excluded.impact,
            forecast     = excluded.forecast,
            previous     = excluded.previous,
            actual       = excluded.actual,
            surprise     = excluded.surprise,
            surprise_pct = excluded.surprise_pct,
            unit         = excluded.unit,
            source       = excluded.source,
            source_raw   = excluded.source_raw
    """
    count = 0
    with get_conn() as conn:
        for r in rows:
            conn.execute(sql, (
                ts_collected,
                r["event_time"], r["country"], r["event_name"], r["impact"],
                r["forecast"], r["previous"], r["actual"],
                r["surprise"], r["surprise_pct"],
                r["unit"], r["source"], r["source_raw"],
            ))
            count += 1
    return count


def collect() -> dict[str, Any]:
    """Coleta calendario economico full + persiste. Idempotente."""
    cfg = _load_config()
    events_by_country = cfg.get("events", {}) or {}
    lookback  = int(cfg.get("lookback_days", 30))
    lookahead = int(cfg.get("lookahead_days", 14))
    delay     = float(cfg.get("request_delay_s", 1.5))
    timeout   = float(cfg.get("request_timeout_s", 30.0))
    max_retries = int(cfg.get("max_retries", 2))          # 1 retry por default
    retry_backoff = float(cfg.get("retry_backoff_s", 4.0))

    # achata: [(country_hint, name, slug), ...]
    flat: list[tuple[str, str, str]] = []
    for country, items in events_by_country.items():
        for it in items or []:
            name = it.get("name")
            slug = it.get("slug")
            if not name or not slug:
                continue
            flat.append((country, name, slug))

    if not flat:
        return {"status": "failed", "error": "config.yaml: calendar.events vazio"}

    now_utc = datetime.now(timezone.utc)
    ts_collected = now_utc.strftime("%Y-%m-%dT%H:%M:%SZ")

    total_ups = 0
    ok = 0
    failures: list[dict] = []

    # Playwright chromium em sessao unica (cookies Cloudflare persistem)
    with CalendarBrowser(timeout=timeout) as cb:
        for i, (country_hint, name, slug) in enumerate(flat):
            if i > 0:
                time.sleep(delay)
            # retry com backoff pra erros transitorios (Cloudflare,
            # timeout). max_retries=2 -> ate 3 tentativas por slug.
            last_ex: Exception | None = None
            for attempt in range(max_retries + 1):
                try:
                    html = fetch_event_html(cb.page, slug,
                                            timeout_ms=int(timeout * 1000))
                    nd = extract_next_data(html)
                    meta, occ = parse_event_page(nd)
                    rows = parse_occurrences(
                        metadata=meta, occurrences=occ,
                        event_name=name, now_utc=now_utc,
                        lookback_days=lookback, lookahead_days=lookahead,
                    )
                    n = _upsert_rows(rows, ts_collected=ts_collected)
                    total_ups += n
                    ok += 1
                    if attempt > 0:
                        _log.info("calendar: %s/%s — %d occurrences upserted "
                                  "(recovered on attempt %d)",
                                  country_hint, name, n, attempt + 1)
                    else:
                        _log.info("calendar: %s/%s — %d occurrences upserted",
                                  country_hint, name, n)
                    last_ex = None
                    break
                except Exception as ex:
                    last_ex = ex
                    if attempt < max_retries:
                        wait = retry_backoff * (attempt + 1)
                        _log.info("calendar retry %d/%d for %s/%s after %.1fs: %s",
                                  attempt + 1, max_retries, country_hint,
                                  name, wait, str(ex)[:120])
                        time.sleep(wait)
            if last_ex is not None:
                _log.warning("calendar failed for %s/%s (%s) after %d attempts: %s",
                             country_hint, name, slug, max_retries + 1, last_ex)
                failures.append({"slug": slug, "country": country_hint,
                                 "name": name, "error": str(last_ex)[:180]})

    if ok == 0:
        status = "failed"
    elif failures:
        status = "partial"
    else:
        status = "ok"

    return {
        "status": status,
        "events_configured": len(flat),
        "events_fetched": ok,
        "events_failed": failures,
        "occurrences_upserted": total_ups,
    }


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    r = collect()
    # resumo sem poluir com failures longos
    r_copy = dict(r)
    if len(r_copy.get("events_failed", [])) > 3:
        r_copy["events_failed"] = r_copy["events_failed"][:3] + [{"_": "..."}]
    print(json.dumps(r_copy, indent=2, default=str))
