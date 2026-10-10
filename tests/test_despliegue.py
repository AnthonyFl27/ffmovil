"""T-119: archivos de la fase 1 del dominio (Caddyfile, página «Próximamente» y Compose).

RNF-18 y CA-09 (CHG-020), con las cabeceras de RNF-14. Sin BD ni red: la verificación
del certificado y de las redirecciones reales se hace en el VPS (CA-09).
"""

import re
from pathlib import Path

from app.cabeceras import CSP

RAIZ = Path(__file__).resolve().parent.parent
DEPLOY = RAIZ / "deploy"
PAGINA = DEPLOY / "proximamente"


def _caddyfile() -> str:
    return (DEPLOY / "Caddyfile.proximamente").read_text(encoding="utf-8")


def _bloque(texto: str, cabecera: str) -> str:
    """Contenido del bloque `cabecera { ... }` de un Caddyfile (sin anidar más de un nivel)."""
    inicio = texto.index(f"\n{cabecera} {{") + len(cabecera) + 3
    return texto[inicio : texto.index("\n}", inicio)]


def test_el_caddyfile_sirve_el_dominio_y_redirige_www_de_forma_permanente():
    """RNF-18, CA-09: `ffmovil.com` canónico; `www` redirige con 301."""
    texto = _caddyfile()
    assert "\nffmovil.com {" in texto
    assert "redir https://ffmovil.com{uri} permanent" in _bloque(texto, "www.ffmovil.com")
    # Sin esquema en las direcciones Caddy redirige solo el HTTP a HTTPS y emite certificado.
    assert "http://" not in texto.replace("https://ffmovil.com{uri}", "")


def test_la_fase_1_no_expone_la_app_ni_lleva_datos_personales():
    """RNF-18: sin `reverse_proxy` a la app; repositorio público: sin correo en el Caddyfile."""
    texto = _caddyfile()
    assert "reverse_proxy" not in texto
    assert "email" not in texto.lower() and "@" not in texto
    assert "protocols h1 h2" in texto  # HTTP/3 lo ofrece Cloudflare, no el origen


def test_el_caddyfile_pone_las_cabeceras_de_seguridad():
    """RNF-14, CA-09: las cuatro cabeceras de la app y sin cabecera `Server`."""
    cabeceras = _bloque(_caddyfile(), "ffmovil.com")
    for linea in (
        "X-Content-Type-Options nosniff",
        "X-Frame-Options DENY",
        "Referrer-Policy same-origin",
        f'Content-Security-Policy "{CSP}"',
        "-Server",
    ):
        assert linea in cabeceras, linea


def test_la_pagina_no_usa_nada_en_linea_ni_recursos_externos():
    """RNF-14, CA-09: compatible con la CSP (`default-src 'self'`)."""
    html = (PAGINA / "index.html").read_text(encoding="utf-8")
    assert "Próximamente" in html and 'lang="es"' in html
    assert not re.search(r"<script|<style|\sstyle=|\son\w+=|https?://|//cdn", html, re.IGNORECASE)
    css = (PAGINA / "estilo.css").read_text(encoding="utf-8")
    assert not re.search(r"@import|url\(|https?://", css, re.IGNORECASE)
    for ruta in re.findall(r'(?:src|href)="([^"]+)"', html):
        assert (PAGINA / ruta).is_file(), ruta


def test_el_compose_publica_solo_80_y_443_desde_caddy_y_sin_depender_de_la_app():
    """RNF-18, CA-09: solo `caddy` publica 80 y 443; se puede levantar sin `app`."""
    compose = (RAIZ / "docker-compose.yml").read_text(encoding="utf-8")
    caddy = compose[compose.index("\n  caddy:") : compose.index("\nnetworks:")]
    assert re.findall(r'- "(\d+:\d+(?:/\w+)?)"', caddy.split("volumes:")[0]) == ["80:80", "443:443"]
    assert "depends_on" not in caddy
    assert "cap_drop:\n      - ALL" in caddy and "NET_BIND_SERVICE" in caddy
    assert "caddy_data:/data" in caddy  # los certificados sobreviven a recrear el contenedor
