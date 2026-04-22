"""Recon: descobre endpoints XHR que a marketplace page da Truflation consome.

Uso:
    python -m recon.truflation_recon

Saida:
    recon/truflation_endpoints.json  — lista de requests (url, method, status,
                                       content-type, preview do body, headers
                                       relevantes)
    recon/truflation_page.html       — HTML final renderizado (pra achar
                                       __NEXT_DATA__ embutido)

Estrategia:
- Abre https://truflation.com/marketplace/us-inflation-rate em Chromium headless
- Captura todo request/response via Page.on('response')
- Filtra por JSON responses com "truflation"/"cpi"/numeros de inflacao (1.77, etc)
- Ao final dumpa o HTML completo da pagina pra inspecao de __NEXT_DATA__
- Nao loga, nao clica em nada — so abre e espera a hydratacao
"""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT))

try:
    from playwright.async_api import async_playwright
except ImportError:
    print("ERROR: playwright nao instalado. Rode: pip install playwright && playwright install chromium")
    sys.exit(1)


URL = "https://truflation.com/marketplace/us-inflation-rate"
OUT_JSON = _REPO_ROOT / "recon" / "truflation_endpoints.json"
OUT_HTML = _REPO_ROOT / "recon" / "truflation_page.html"

# Termos que provavelmente aparecem no JSON do index
INTERESTING_TERMS = ("truflation", "trucpi", "inflation", "cpi", "index", "value")


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
        )
        page = await context.new_page()

        async def on_response(resp):
            try:
                url = resp.url
                ctype = (resp.headers.get("content-type") or "").lower()
                status = resp.status
                # filtra ruido obvio (assets, fonts, img)
                if any(url.endswith(ext) for ext in (".js", ".css", ".woff", ".woff2",
                                                     ".png", ".jpg", ".jpeg", ".svg",
                                                     ".ico", ".webp", ".gif", ".map")):
                    return
                if "image/" in ctype or "font/" in ctype:
                    return

                entry: dict = {
                    "url": url,
                    "method": resp.request.method,
                    "status": status,
                    "content_type": ctype,
                    "resource_type": resp.request.resource_type,
                    "request_headers": {
                        k: v for k, v in resp.request.headers.items()
                        if k.lower() in ("authorization", "x-api-key", "cookie",
                                         "referer", "origin", "accept")
                    },
                }

                # tenta pegar preview do body se for JSON ou texto pequeno
                if "json" in ctype or "text" in ctype:
                    try:
                        body = await resp.text()
                        entry["body_len"] = len(body)
                        entry["body_preview"] = body[:4000]
                        # flag se tem termo interessante
                        low = body.lower()
                        entry["has_interesting_term"] = any(t in low for t in INTERESTING_TERMS)
                    except Exception as ex:
                        entry["body_error"] = str(ex)

                captured.append(entry)
            except Exception as ex:
                captured.append({"url": resp.url, "capture_error": str(ex)})

        page.on("response", on_response)

        print(f"Navegando para {URL} ...")
        await page.goto(URL, wait_until="networkidle", timeout=60000)

        # espera extra pra XHRs lazy (chart data)
        await asyncio.sleep(5)

        # clica em outros intervalos pra forcar carregamento de mais pontos
        for label in ("5Y", "MAX"):
            try:
                await page.get_by_text(label, exact=True).first.click(timeout=3000)
                await asyncio.sleep(2)
            except Exception as ex:
                print(f"  nao clicou em {label}: {ex}")

        html = await page.content()
        OUT_HTML.write_text(html, encoding="utf-8")
        print(f"HTML salvo em {OUT_HTML} ({len(html)} bytes)")

        await browser.close()

    # ordena: interessantes primeiro
    captured.sort(key=lambda e: (not e.get("has_interesting_term", False), e.get("url", "")))

    OUT_JSON.write_text(
        json.dumps(captured, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    total = len(captured)
    interesting = sum(1 for e in captured if e.get("has_interesting_term"))
    print(f"\nCapturadas {total} responses ({interesting} com termos relevantes)")
    print(f"JSON: {OUT_JSON}")

    # print top 10 interessantes
    print("\nTop URLs com termo relevante:")
    for e in captured[:15]:
        if e.get("has_interesting_term"):
            print(f"  [{e.get('status')}] {e.get('method')} {e.get('url')[:120]}")

    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
