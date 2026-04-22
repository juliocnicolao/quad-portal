"""Recon: unusualwhales.com stock overview — descobre endpoints + shape.

Uso:
    python -m recon.unusual_whales_recon [TICKER]   # default: PBR

Saida:
    recon/unusual_whales_<ticker>_endpoints.json    — XHRs capturadas
    recon/unusual_whales_<ticker>_page.html         — HTML renderizado

Estrategia:
- Abre https://unusualwhales.com/stock/{TICKER}/overview?chart=options-volume
  em Chromium headless, com as mesmas flags anti-deteccao do calendar.
- Captura todo XHR/fetch (method, url, status, content-type, body preview).
- Interage com o chart (se possivel) pra provocar a carga de GEX e series
  de options flow.
"""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT))

from playwright.async_api import async_playwright

BASE_URL = "https://unusualwhales.com/stock/{ticker}/overview?chart=options-volume"

INTERESTING = (
    "flow", "options", "greek", "gex", "gamma", "premium",
    "volume", "iv", "oi", "put", "call", "strike", "expiry",
    "ticker", "chart", "ohlc", "pc", "ratio",
)


async def main() -> int:
    ticker = (sys.argv[1] if len(sys.argv) > 1 else "PBR").upper()
    url = BASE_URL.format(ticker=ticker)
    out_json = _REPO_ROOT / "recon" / f"unusual_whales_{ticker.lower()}_endpoints.json"
    out_html = _REPO_ROOT / "recon" / f"unusual_whales_{ticker.lower()}_page.html"

    captured: list[dict] = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--disable-dev-shm-usage",
                "--no-sandbox",
            ],
        )
        context = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/131.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1440, "height": 900},
            locale="en-US",
        )
        await context.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', { get: () => undefined });"
        )
        page = await context.new_page()

        async def on_response(resp):
            try:
                u = resp.url
                ctype = (resp.headers.get("content-type") or "").lower()
                if any(u.endswith(x) for x in (".js", ".css", ".woff", ".woff2",
                                                ".png", ".jpg", ".svg", ".ico",
                                                ".webp", ".gif", ".map")):
                    return
                if "image/" in ctype or "font/" in ctype or "video/" in ctype:
                    return

                entry: dict = {
                    "url": u,
                    "method": resp.request.method,
                    "status": resp.status,
                    "content_type": ctype,
                    "resource_type": resp.request.resource_type,
                }
                if "json" in ctype or "text" in ctype or "html" in ctype:
                    try:
                        body = await resp.text()
                        entry["body_len"] = len(body)
                        entry["body_preview"] = body[:4000]
                        low = body.lower()
                        entry["has_interesting_term"] = any(t in low for t in INTERESTING)
                    except Exception as ex:
                        entry["body_error"] = str(ex)

                if resp.request.method == "POST":
                    try:
                        entry["post_data"] = resp.request.post_data
                    except Exception:
                        pass

                captured.append(entry)
            except Exception as ex:
                captured.append({"url": resp.url, "capture_error": str(ex)})

        page.on("response", on_response)

        print(f"Navegando para {url} ...")
        await page.goto(url, wait_until="domcontentloaded", timeout=60000)
        await asyncio.sleep(5)

        # tentativa de trocar chart pra daily GEX e pra options-volume
        for chart_key in ("daily-gex", "net-premium-ticks", "options-volume"):
            try:
                target = url.split("?")[0] + f"?chart={chart_key}"
                print(f"  navegando pra chart={chart_key} ...")
                await page.goto(target, wait_until="domcontentloaded", timeout=45000)
                await asyncio.sleep(4)
            except Exception as ex:
                print(f"  falhou {chart_key}: {ex}")

        # scroll pra carregar tudo
        for _ in range(3):
            try:
                await page.mouse.wheel(0, 2000)
                await asyncio.sleep(1)
            except Exception:
                pass

        html = await page.content()
        out_html.write_text(html, encoding="utf-8")
        print(f"HTML salvo ({len(html)} bytes)")

        await browser.close()

    captured.sort(key=lambda e: (not e.get("has_interesting_term", False),
                                  e.get("url", "")))
    out_json.write_text(json.dumps(captured, indent=2, ensure_ascii=False),
                        encoding="utf-8")

    total = len(captured)
    hot = sum(1 for e in captured if e.get("has_interesting_term"))
    print(f"\nCapturadas {total} responses ({hot} interessantes)")
    print(f"JSON: {out_json}\n")

    print("Top URLs com termo relevante:")
    for e in captured[:30]:
        if e.get("has_interesting_term"):
            status = e.get("status")
            meth = e.get("method")
            uu = e.get("url", "")[:140]
            blen = e.get("body_len", 0)
            print(f"  [{status}] {meth} {uu}  ({blen}B)")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
