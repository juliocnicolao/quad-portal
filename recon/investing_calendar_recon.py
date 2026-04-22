"""Recon: investing.com economic calendar — descobre endpoints + shape.

Uso:
    python -m recon.investing_calendar_recon

Saida:
    recon/investing_calendar_endpoints.json  — XHRs capturadas
    recon/investing_calendar_page.html       — HTML renderizado final

Estrategia:
- Abre https://www.investing.com/economic-calendar/ em Chromium headless
- Filtra apenas high-impact (3 bulls) pra ver o endpoint que os filtros usam
- Tenta clicar em "This Week" pra ver request de range maior
- Captura todo response de XHR/fetch
"""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT))

from playwright.async_api import async_playwright

URL = "https://www.investing.com/economic-calendar/"
OUT_JSON = _REPO_ROOT / "recon" / "investing_calendar_endpoints.json"
OUT_HTML = _REPO_ROOT / "recon" / "investing_calendar_page.html"

INTERESTING = ("calendar", "event", "economic", "cpi", "payroll", "fomc",
               "forecast", "actual", "previous", "importance")


async def main() -> int:
    captured: list[dict] = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/131.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1440, "height": 900},
            locale="en-US",
        )
        page = await context.new_page()

        async def on_response(resp):
            try:
                url = resp.url
                ctype = (resp.headers.get("content-type") or "").lower()
                if any(url.endswith(x) for x in (".js", ".css", ".woff", ".woff2",
                                                  ".png", ".jpg", ".svg", ".ico",
                                                  ".webp", ".gif", ".map")):
                    return
                if "image/" in ctype or "font/" in ctype:
                    return

                entry: dict = {
                    "url": url,
                    "method": resp.request.method,
                    "status": resp.status,
                    "content_type": ctype,
                    "resource_type": resp.request.resource_type,
                }
                if "json" in ctype or "html" in ctype or "text" in ctype:
                    try:
                        body = await resp.text()
                        entry["body_len"] = len(body)
                        entry["body_preview"] = body[:3000]
                        low = body.lower()
                        entry["has_interesting_term"] = any(t in low for t in INTERESTING)
                    except Exception as ex:
                        entry["body_error"] = str(ex)

                # capture POST body se houver
                if resp.request.method == "POST":
                    try:
                        entry["post_data"] = resp.request.post_data
                    except Exception:
                        pass

                captured.append(entry)
            except Exception as ex:
                captured.append({"url": resp.url, "capture_error": str(ex)})

        page.on("response", on_response)

        print(f"Navegando para {URL} ...")
        await page.goto(URL, wait_until="domcontentloaded", timeout=60000)
        await asyncio.sleep(4)

        # Tenta aceitar cookies (investing.com tem banner OneTrust)
        for label in ("Accept All", "I Accept", "Accept", "AGREE"):
            try:
                await page.get_by_text(label, exact=False).first.click(timeout=2000)
                await asyncio.sleep(1)
                print(f"  cookies: cliquei em '{label}'")
                break
            except Exception:
                pass

        # Tenta ativar filtro "This Week" ou similar
        for label in ("This Week", "Next Week", "Tomorrow"):
            try:
                await page.get_by_text(label, exact=True).first.click(timeout=3000)
                await asyncio.sleep(2)
                print(f"  cliquei em '{label}'")
                break
            except Exception:
                pass

        # scroll pra carregar mais
        for _ in range(3):
            await page.mouse.wheel(0, 2000)
            await asyncio.sleep(1)

        html = await page.content()
        OUT_HTML.write_text(html, encoding="utf-8")
        print(f"HTML salvo ({len(html)} bytes)")

        await browser.close()

    captured.sort(key=lambda e: (not e.get("has_interesting_term", False),
                                  e.get("url", "")))
    OUT_JSON.write_text(json.dumps(captured, indent=2, ensure_ascii=False),
                        encoding="utf-8")

    total = len(captured)
    hot = sum(1 for e in captured if e.get("has_interesting_term"))
    print(f"\nCapturadas {total} responses ({hot} interessantes)")
    print(f"JSON: {OUT_JSON}\n")

    print("Top URLs com termo relevante:")
    for e in captured[:20]:
        if e.get("has_interesting_term"):
            status = e.get("status")
            meth = e.get("method")
            url = e.get("url", "")[:130]
            blen = e.get("body_len", 0)
            print(f"  [{status}] {meth} {url}  ({blen}B)")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
