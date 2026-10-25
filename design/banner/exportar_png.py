"""Exporta el banner a PNG estático (995 × 340) congelando la animación en un cuadro fijo.

Uso (después de generar.py):
  uv run --with playwright python design/banner/exportar_png.py
Requiere Chromium de Playwright (`uv run playwright install chromium`).
"""

from pathlib import Path

from playwright.sync_api import sync_playwright

SALIDA = Path(__file__).resolve().parent / "salida"
CUADRO_MS = 3000  # ya entró todo (≈1.6 s) y el celular aún muestra la portada (0–4.2 s)

with sync_playwright() as p:
    nav = p.chromium.launch()
    pag = nav.new_page(viewport={"width": 995, "height": 340})
    pag.goto((SALIDA / "banner.svg").as_uri())
    pag.evaluate(
        "ms => document.getAnimations().forEach(a => { a.pause(); a.currentTime = ms; })", CUADRO_MS
    )
    pag.wait_for_timeout(300)
    pag.screenshot(path=str(SALIDA / "banner.png"))
    nav.close()
print(f"banner.png: {(SALIDA / 'banner.png').stat().st_size / 1024:.0f} KB")
