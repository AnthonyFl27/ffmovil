"""Genera el banner «Somos distribuidor» de FFmovil (995 × 340) para el panel de Dhru Fusion.

Salida (en esta carpeta, `salida/`):
  - banner.svg          SVG animado, autocontenido (imágenes en base64, texto convertido a trazos).
  - banner-dhru.txt     Valor para el campo «SVG or base64» de Dhru: url("data:image/svg+xml,...").
  - banner-dhru-b64.txt El mismo valor con base64 (por si el panel rechaza el anterior).

Uso:  uv run --with fonttools --with pillow python design/banner/generar.py

Dhru usa el SVG como fondo CSS (como una imagen): no corre JavaScript, no hay hover ni clic dentro del
SVG y no se cargan recursos externos. Por eso todo va incrustado y las animaciones son CSS puras.
"""

from __future__ import annotations

import base64
import io
import random
import re
from pathlib import Path

from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.pens.transformPen import TransformPen
from fontTools.ttLib import TTFont
from PIL import Image

RAIZ = Path(__file__).resolve().parents[2]
ESTATICO = RAIZ / "app" / "static"
SALIDA = Path(__file__).resolve().parent / "salida"

ANCHO, ALTO = 995, 340

FUENTES = {
    "negra": "/usr/share/fonts/google-noto/NotoSans-Black.ttf",
    "negrita": "/usr/share/fonts/google-noto/NotoSans-Bold.ttf",
    "media": "/usr/share/fonts/google-noto/NotoSans-Medium.ttf",
}
_fuentes: dict[str, TTFont] = {}


# --------------------------------------------------------------------------- texto en trazos


def _fuente(clave: str) -> TTFont:
    if clave not in _fuentes:
        _fuentes[clave] = TTFont(FUENTES[clave])
    return _fuentes[clave]


def _num(v: float) -> str:
    return f"{v:.2f}".rstrip("0").rstrip(".")


def medir(clave: str, texto: str, tam: float, espaciado: float = 0) -> float:
    f = _fuente(clave)
    esc = tam / f["head"].unitsPerEm
    gs, cmap = f.getGlyphSet(), f.getBestCmap()
    return sum(gs[cmap[ord(c)]].width * esc + espaciado for c in texto) - espaciado


def trazos(
    clave: str,
    texto: str,
    tam: float,
    x: float,
    y: float,
    ancla: str = "inicio",
    espaciado: float = 0,
) -> str:
    """Devuelve el atributo `d` de un path con el texto dibujado en (x, y = línea base)."""
    f = _fuente(clave)
    esc = tam / f["head"].unitsPerEm
    gs, cmap = f.getGlyphSet(), f.getBestCmap()
    ancho = medir(clave, texto, tam, espaciado)
    cx = x - (ancho / 2 if ancla == "centro" else ancho if ancla == "fin" else 0)
    pen = SVGPathPen(gs, ntos=_num)
    for c in texto:
        g = gs[cmap[ord(c)]]
        g.draw(TransformPen(pen, (esc, 0, 0, -esc, cx, y)))
        cx += g.width * esc + espaciado
    return pen.getCommands()


# --------------------------------------------------------------------------- imágenes


def imagen(ruta: str, ancho: int, calidad: int = 82) -> tuple[str, int, int]:
    """WebP redimensionado a `ancho` px, en base64. Devuelve (data URI, ancho, alto)."""
    im = Image.open(ESTATICO / ruta).convert("RGBA")
    alto = round(im.height * ancho / im.width)
    im = im.resize((ancho, alto), Image.LANCZOS)
    buf = io.BytesIO()
    im.save(buf, "WEBP", quality=calidad, method=6)
    return "data:image/webp;base64," + base64.b64encode(buf.getvalue()).decode(), ancho, alto


def logo_circular(ancho: int) -> str:
    im = Image.open(ESTATICO / "logo.png").convert("RGBA").resize((ancho, ancho), Image.LANCZOS)
    buf = io.BytesIO()
    im.save(buf, "WEBP", quality=90, method=6)
    return "data:image/webp;base64," + base64.b64encode(buf.getvalue()).decode()


def nombre_svg() -> str:
    """Los trazos del nombre «ffmovil» (app/static/nombre.svg), sin la etiqueta <svg>."""
    texto = (ESTATICO / "nombre.svg").read_text()
    return re.sub(r"</?svg[^>]*>|<title>.*?</title>", "", texto).replace('"', "'")


# --------------------------------------------------------------------------- piezas


def destello(
    cx: float, cy: float, r: float, clase: str, retraso: float, color: str = "#ffffff"
) -> str:
    d = f"M0 {-r}C{r * 0.12:.1f} {-r * 0.12:.1f} {r * 0.12:.1f} {-r * 0.12:.1f} {r} 0C{r * 0.12:.1f} {r * 0.12:.1f} {r * 0.12:.1f} {r * 0.12:.1f} 0 {r}C{-r * 0.12:.1f} {r * 0.12:.1f} {-r * 0.12:.1f} {r * 0.12:.1f} {-r} 0C{-r * 0.12:.1f} {-r * 0.12:.1f} {-r * 0.12:.1f} {-r * 0.12:.1f} 0 {-r}Z"
    return f"<g transform='translate({cx} {cy})'><path class='{clase}' style='animation-delay:{retraso}s' fill='{color}' d='{d}'/></g>"


def gema(cx: float, cy: float, t: float, clase: str, retraso: float) -> str:
    """Rombo facetado pequeño (el diamante de la marca) que sube y se desvanece."""
    return (
        f"<g transform='translate({cx} {cy})'><g class='{clase}' style='animation-delay:{retraso}s'>"
        f"<path d='M0 {-t}L{t * 0.8:.1f} 0L0 {t}L{-t * 0.8:.1f} 0Z' fill='#4aa8ff'/>"
        f"<path d='M0 {-t}L{t * 0.8:.1f} 0L0 0Z' fill='#c4e9ff'/>"
        f"<path d='M0 {-t}L{-t * 0.8:.1f} 0L0 0Z' fill='#5cb8ff'/>"
        f"<path d='M0 {t}L{t * 0.8:.1f} 0L0 0Z' fill='#2563e2'/></g></g>"
    )


def campo_de_simbolos() -> tuple[str, str]:
    """Caracteres griegos, matemáticos y de código como en la portada: <defs> con cada glifo y los <use>.

    Mucho más densos en el lado izquierdo (fondo oscuro), de tamaños distintos y atenuados detrás del
    título, el botón y el pie para no restarles legibilidad.
    """
    simbolos = "αβγδεζηθλμπσφψωΣΔΩΠ∑∞≈≠±√∫∂→⇒∴⊕01010101<>/+=*{}[]#%&;"
    rnd = random.Random(11)
    defs, usos = [], []
    cmap = _fuente("media").getBestCmap()
    disponibles = [c for c in simbolos if ord(c) in cmap]
    for i, c in enumerate(disponibles):
        defs.append(f"<path id='s{i}' d='{trazos('media', c, 13, 0, 0)}'/>")

    def atenuacion(x: float, y: float) -> float:
        """Menos opacidad donde hay texto del banner."""
        if 28 <= x <= 482 and 86 <= y <= 222:  # título
            return 0.28
        if 28 <= x <= 335 and 250 <= y <= 312:  # logo y botón
            return 0.3
        if 28 <= x <= 440 and 318 <= y <= 337:  # pie
            return 0.4
        if 28 <= x <= 210 and 22 <= y <= 66:  # logo de Free Fire
            return 0.35
        return 1.0

    def colocar(
        n: int, x_min: float, x_max: float, sesgo: float, tam_min: float, tam_max: float, extra: int
    ) -> None:
        for k in range(n):
            y = ALTO * (rnd.random() ** sesgo)  # sesgo < 1: más densos abajo
            x = rnd.uniform(x_min, x_max)
            t = rnd.uniform(tam_min, tam_max) / 13
            op = (0.28 + 0.6 * (y / ALTO) ** 1.1) * atenuacion(x, y) * rnd.uniform(0.75, 1.0)
            color = rnd.choice(("#9fc2ff", "#9fc2ff", "#6aa5ff", "#4d8dff", "#c4d6ff"))
            movil = " deriva" if rnd.random() < 0.14 else ""
            usos.append(
                f"<g transform='translate({x:.0f} {y:.0f}) scale({t:.2f})'><use href='#s{rnd.randrange(len(disponibles))}' "
                f"class='sim g{(k + extra) % 4}{movil}' fill='{color}' opacity='{op:.2f}'/></g>"
            )

    colocar(300, 4, 500, 0.8, 8, 17, 0)  # lado izquierdo: denso
    colocar(60, 500, ANCHO - 6, 0.85, 8, 13, 1)  # resto: como antes
    return "".join(defs), "".join(usos)


def trazos_de_circuito() -> str:
    """Líneas finas tipo circuito con nodos; un pulso de luz las recorre."""
    rutas = [
        "M4 50H70L90 70H196",
        "M230 20H300L318 38H470",
        "M4 236H34L52 220H100",
        "M350 236H400L418 252H488",
        "M420 120H478L494 104",
        "M4 128H22L34 140H60",
        "M260 330H340L352 318H470",
    ]
    nodos = [(196, 70), (470, 38), (100, 220), (488, 252), (494, 104), (60, 140), (470, 318)]
    base = "".join(
        f"<path d='{d}' fill='none' stroke='#3f7dff' stroke-opacity='.35' stroke-width='1'/>"
        for d in rutas
    )
    pulsos = "".join(
        f"<path class='pulso-c' style='animation-delay:{-i * 1.3}s' d='{d}' pathLength='100' fill='none' stroke='#9fd0ff' "
        "stroke-width='1.8' stroke-linecap='round'/>"
        for i, d in enumerate(rutas)
    )
    puntos = "".join(
        f"<circle cx='{x}' cy='{y}' r='2.2' fill='#0a1a45' stroke='#6aa5ff' stroke-width='1'/>"
        for x, y in nodos
    )
    return base + pulsos + puntos


def pantalla_inicio(
    img_pj: tuple[str, int, int], img_dia: tuple[str, int, int], img_ff: tuple[str, int, int]
) -> str:
    """Portada nueva de la web (tarjeta azul): logo, titular con «vender diamantes» resaltado, apoyo, caja y personaje."""
    resalte, blanco = "#c4d6ff", "#ffffff"
    titular = [
        [("Ya puedes ", blanco), ("vender", resalte)],
        [("diamantes", resalte), (" a tus", blanco)],
        [("propios clientes usando", blanco)],
        [("nuestros precios y", blanco)],
        [("nuestra plataforma.", blanco)],
    ]
    x0, tam = -62, 8.6
    texto = ""
    for i, segmentos in enumerate(titular):
        x = x0
        for trozo, color in segmentos:
            texto += (
                f"<path d='{trazos('negrita', trozo, tam, x, -66 + i * 10.6)}' fill='{color}'/>"
            )
            x += medir("negrita", trozo, tam)
    apoyo = "".join(
        f"<path d='{trazos('media', t, 5.8, x0, -10 + i * 7.4)}' fill='#dbe5ff'/>"
        for i, t in enumerate(
            [
                "Cuenta prepago, recarga con el",
                "Player ID y tus pedidos siempre",
                "a la vista, desde el celular.",
            ]
        )
    )
    # personaje (cara visible) con los diamantes sobre la palma, como en la portada
    pj_ancho = 104
    pj_alto = round(img_pj[2] * pj_ancho / img_pj[1])
    pj_x, pj_y = -14, 138 - pj_alto
    dia_ancho = round(pj_ancho * 0.22 * 1.3)
    dia_alto = round(img_dia[2] * dia_ancho / img_dia[1])
    # caja «¿Aún no tienes usuario?» (delante del personaje, abajo a la izquierda)
    caja = (
        "<rect x='-64' y='58' width='62' height='72' rx='7' fill='#0c2377' fill-opacity='.82' stroke='#fff' stroke-opacity='.18'/>"
        f"<path d='{trazos('negrita', '¿Aún no tienes', 5.6, -58, 72)}' fill='#fff'/>"
        f"<path d='{trazos('negrita', 'usuario?', 5.6, -58, 79)}' fill='#fff'/>"
        + "".join(
            f"<path d='{trazos('media', t, 4.1, -58, 88 + i * 5.4)}' fill='#b9c7ee'/>"
            for i, t in enumerate(
                ["Contáctate con uno de", "nuestros revendedores", "y empieza a vender."]
            )
        )
        + "<rect x='-58' y='108' width='50' height='14' rx='4' fill='#fff'/>"
        f"<path d='{trazos('negrita', 'Ver revendedores', 4.9, -33, 117, 'centro')}' fill='#0a1124'/>"
    )
    return (
        "<g class='pantalla pa'>"
        "<rect x='-71' y='-101' width='142' height='238' rx='13' fill='url(#gTarjeta)'/>"
        "<rect x='-71' y='-101' width='142' height='238' rx='13' fill='url(#puntos)'/>"
        "<g clip-path='url(#recTarjeta)'>"
        f"<image href='{img_ff[0]}' x='{x0}' y='-93' width='56' height='{round(img_ff[2] * 56 / img_ff[1])}'/>"
        f"{texto}{apoyo}"
        f"<image href='{img_pj[0]}' x='{pj_x}' y='{pj_y}' width='{pj_ancho}' height='{pj_alto}'/>"
        f"<image class='flotar' href='{img_dia[0]}' x='{pj_x - 2}' y='{pj_y + round(pj_alto * 0.195) - 4}' "
        f"width='{dia_ancho}' height='{dia_alto}'/>"
        f"{caja}"
        "</g></g>"
    )


def pantalla_playerid() -> str:
    titulo = trazos("negrita", "Ingresa tu Player ID", 11.5, 0, -76, "centro")
    sub = trazos("media", "Recarga en tres pasos", 8.6, 0, -60, "centro")
    id_ = trazos("negrita", "1 2 3 4 5 6 7 8 9", 14, 0, -6, "centro")
    boton = trazos("negrita", "Validar", 10.5, 0, 43, "centro")
    paq = ""
    for i, (txt, y) in enumerate((("Elige tu paquete", 74),)):
        paq += (
            f"<path class='chip' d='{trazos('negrita', txt, 9.5, 0, y, 'centro')}' fill='#aab6d6'/>"
        )
    chips = ""
    for i, x in enumerate((-46, 0, 46)):
        chips += (
            f"<g class='chip' style='animation-delay:{i * 0.25}s'>"
            f"<rect x='{x - 20}' y='84' width='40' height='34' rx='8' fill='#12255a' stroke='#2f6bff' stroke-width='1'/>"
            f"<path d='M{x} 92l7 8l-7 9l-7 -9z' fill='#4aa8ff'/><path d='M{x} 92l7 8h-14z' fill='#c4e9ff'/></g>"
        )
    return (
        "<g class='pantalla pb'>"
        f"<path d='{titulo}' fill='#fff'/><path d='{sub}' fill='#aab6d6'/>"
        "<rect x='-58' y='-30' width='116' height='34' rx='9' fill='#0d1a40' stroke='#2f6bff' stroke-width='1.2'/>"
        f"<path d='{id_}' fill='#fff'/>"
        "<rect class='escribe' x='-58' y='-30' width='116' height='34' rx='9' fill='#0d1a40'/>"
        "<rect x='-58' y='24' width='116' height='28' rx='8' fill='#2d66f0'/>"
        f"<path d='{boton}' fill='#fff'/>"
        f"{paq}{chips}"
        "</g>"
    )


def pantalla_lista() -> str:
    titulo = trazos("negra", "¡Recarga lista!", 13, 0, 4, "centro")
    sub = trazos("media", "Tus diamantes ya se acreditaron", 8.4, 0, 22, "centro")
    sub2 = trazos("media", "Player ID 123456789", 8.4, 0, 37, "centro")
    return (
        "<g class='pantalla pc'>"
        "<circle cx='0' cy='-62' r='34' fill='#0f2d78' opacity='.55' class='aro'/>"
        "<circle cx='0' cy='-62' r='25' fill='#1fa463'/>"
        "<path class='visto' d='M-11 -62l8 9l16 -18' fill='none' stroke='#fff' stroke-width='5' stroke-linecap='round' stroke-linejoin='round'/>"
        f"<path d='{titulo}' fill='#fff'/><path d='{sub}' fill='#aab6d6'/><path d='{sub2}' fill='#8fb0ff'/>"
        "<g transform='translate(0 74) scale(.9)'>"
        "<g class='gema-lista'>"
        "<path d='M0 -18L22 0L0 18L-22 0Z' fill='#4aa8ff'/><path d='M0 -18L22 0L0 0Z' fill='#c4e9ff'/>"
        "<path d='M0 -18L-22 0L0 0Z' fill='#5cb8ff'/><path d='M0 18L22 0L0 0Z' fill='#2563e2'/></g></g>"
        "</g>"
    )


CSS = """
.sim{animation:titila 4.8s ease-in-out infinite}
.deriva{animation:titila 4.8s ease-in-out infinite,deriva 9s ease-in-out infinite}
@keyframes deriva{0%,100%{transform:translateY(0)}50%{transform:translateY(-6px)}}
.pulso-c{stroke-dasharray:6 94;animation:pulsoC 4.2s linear infinite}
@keyframes pulsoC{from{stroke-dashoffset:6}to{stroke-dashoffset:-100}}
.rejilla-r{animation:rejilla 7s ease-in-out infinite}
@keyframes rejilla{0%,100%{opacity:.5}50%{opacity:.9}}
.g1{animation-delay:-1.2s}.g2{animation-delay:-2.4s}.g3{animation-delay:-3.6s}
@keyframes titila{0%,100%{fill-opacity:.25}50%{fill-opacity:1}}
.d1{animation:sube 9s linear infinite}
@keyframes sube{0%{transform:translateY(24px) rotate(0);opacity:0}15%{opacity:.85}85%{opacity:.85}100%{transform:translateY(-300px) rotate(40deg);opacity:0}}
.sp{animation:chispa 2.6s ease-in-out infinite;transform:scale(0)}
@keyframes chispa{0%,100%{transform:scale(0) rotate(0);opacity:0}45%{transform:scale(1) rotate(45deg);opacity:1}70%{transform:scale(.3) rotate(90deg);opacity:.4}}
.reflejo{animation:reflejo 6s ease-in-out infinite;opacity:0}
@keyframes reflejo{0%,45%{transform:translateX(0);opacity:0}50%{opacity:.8}75%{opacity:.8}85%,100%{transform:translateX(300px);opacity:0}}
.haz{animation:barrido 7s ease-in-out infinite}
@keyframes barrido{0%{transform:translateX(-420px);opacity:0}15%{opacity:1}60%{opacity:1}100%{transform:translateX(520px);opacity:0}}
.entra-izq{animation:entraI .9s cubic-bezier(.2,.8,.2,1) both}
.entra-der{animation:entraD 1s cubic-bezier(.2,.8,.2,1) both}
.entra-arr{animation:entraA .9s cubic-bezier(.2,.8,.2,1) both}
@keyframes entraI{from{transform:translateX(-60px);opacity:0}to{transform:none;opacity:1}}
@keyframes entraD{from{transform:translateX(90px);opacity:0}to{transform:none;opacity:1}}
@keyframes entraA{from{transform:translateY(40px);opacity:0}to{transform:none;opacity:1}}
.flota{animation:flota 5s ease-in-out infinite}
.flota2{animation:flota 6s ease-in-out -2s infinite}
.flota3{animation:flota 4.2s ease-in-out -1s infinite}
@keyframes flota{0%,100%{transform:translateY(0)}50%{transform:translateY(-7px)}}
.flotar{animation:flotar 4s ease-in-out infinite}
@keyframes flotar{0%,100%{transform:translateY(-3px)}50%{transform:translateY(3px)}}
.mece{animation:mece 6s ease-in-out infinite}
@keyframes mece{0%,100%{transform:rotate(-1.2deg)}50%{transform:rotate(1.2deg)}}
.barre-t{animation:barreT 5s ease-in-out infinite}
@keyframes barreT{0%,55%{transform:translateX(0)}95%,100%{transform:translateX(520px)}}
.destello-b{animation:destelloB 3.2s ease-in-out infinite}
@keyframes destelloB{0%,35%{transform:translateX(-80px)}75%,100%{transform:translateX(260px)}}
.pulso{animation:pulso 2.4s ease-in-out infinite}
@keyframes pulso{0%,100%{transform:scale(1)}50%{transform:scale(1.035)}}
.flecha{animation:flecha 1.4s ease-in-out infinite}
@keyframes flecha{0%,100%{transform:translateX(0)}50%{transform:translateX(5px)}}
.pantalla{opacity:0}
.pa{animation:verA 14s ease-in-out infinite}
.pb{animation:verB 14s ease-in-out infinite}
.pc{animation:verC 14s ease-in-out infinite}
@keyframes verA{0%,30%{opacity:1}34%,94%{opacity:0}98%,100%{opacity:1}}
@keyframes verB{0%,32%{opacity:0}37%,62%{opacity:1}66%,100%{opacity:0}}
@keyframes verC{0%,64%{opacity:0}69%,92%{opacity:1}96%,100%{opacity:0}}
.escribe{transform-box:fill-box;transform-origin:100% 50%;animation:escribe 14s steps(9,end) infinite}
@keyframes escribe{0%,37%{transform:scaleX(1)}50%,100%{transform:scaleX(0)}}
.chip{animation:chip 14s ease-in-out infinite;opacity:0}
@keyframes chip{0%,50%{opacity:0;transform:translateY(8px)}56%,62%{opacity:1;transform:none}66%,100%{opacity:0}}
.visto{stroke-dasharray:44;animation:visto 14s ease-out infinite}
@keyframes visto{0%,68%{stroke-dashoffset:44}76%,100%{stroke-dashoffset:0}}
.aro{transform-box:fill-box;transform-origin:center;animation:aro 2s ease-out infinite}
@keyframes aro{0%{transform:scale(.7);opacity:.7}100%{transform:scale(1.25);opacity:0}}
.gema-lista{animation:gemaL 2.4s ease-in-out infinite}
@keyframes gemaL{0%,100%{transform:translateY(0) scale(1)}50%{transform:translateY(-6px) scale(1.08)}}
.cursor{animation:cursor 1s steps(1) infinite}
@keyframes cursor{50%{opacity:0}}
@media (prefers-reduced-motion:reduce){*{animation:none!important}.pantalla{opacity:0}.pa{opacity:1}}
"""


def construir() -> str:
    # --- imágenes (anchos = ~1.5× lo que se muestra, para que se vean nítidas sin pesar de más)
    pj1 = imagen("inicio/personaje-1.webp", 380)
    pj2 = imagen("inicio/personaje-2.webp", 200)
    pj3 = imagen("inicio/personaje-3.webp", 360)
    dia = imagen("inicio/diamantes.webp", 120)
    dia_g = imagen("inicio/diamantes.webp", 140)
    cofre = imagen("inicio/cofre.webp", 210)
    ff_grande = imagen("inicio/freefire-blanco.webp", 320)
    ff_chico = imagen("inicio/freefire-blanco.webp", 180)
    logo = logo_circular(120)

    defs_simbolos, usos_simbolos = campo_de_simbolos()
    nombre = nombre_svg()

    # --- texto principal
    tam = 62
    ancho_dist = medir("negra", "DISTRIBUIDOR", tam, 0.5)
    escala = 436 / ancho_dist
    tam_d = tam * escala
    somos = trazos("negra", "SOMOS", tam_d, 36, 142, espaciado=0.5)
    distrib = trazos("negra", "DISTRIBUIDOR", tam_d, 36, 142 + tam_d * 0.93, espaciado=0.5)
    sub = trazos(
        "media", "Recarga con el Player ID, desde el celular o tu computadora.", 12.6, 38, 331
    )
    boton_txt = trazos("negra", "ffmovil.com", 21, 124, 289)
    ff_alto = round(ff_grande[2] * 168 / ff_grande[1])

    # --- elementos del fondo
    chispas = "".join(
        destello(x, y, r, "sp", d)
        for x, y, r, d in (
            (520, 52, 11, 0.2),
            (700, 112, 11, 1.1),
            (934, 32, 10, 0.6),
            (968, 160, 8, 1.7),
            (610, 22, 7, 2.1),
            (455, 215, 7, 0.9),
            (840, 20, 7, 1.4),
            (748, 300, 9, 2.2),
            (480, 120, 6, 1.9),
            (560, 330, 6, 0.4),
        )
    )
    gemas = "".join(
        gema(x, 330, t, "d1", d)
        for x, t, d in (
            (470, 7, 0),
            (545, 5, -2),
            (640, 8, -4.5),
            (735, 6, -1.2),
            (820, 9, -6),
            (905, 5, -3.3),
            (975, 7, -7.7),
        )
    )

    # --- celular
    pa = pantalla_inicio(pj2, dia, ff_chico)
    pb = pantalla_playerid()
    pc = pantalla_lista()
    celular = f"""
<g transform='translate(587 168) rotate(-4)'><g class='mece'>
  <rect x='-84' y='-148' width='168' height='296' rx='28' fill='#070c1c' stroke='#3f68d8' stroke-width='2.2'/>
  <rect x='-84' y='-148' width='168' height='296' rx='28' fill='none' stroke='#9fc2ff' stroke-opacity='.25' stroke-width='.8' transform='scale(.985)'/>
  <clipPath id='pantalla'><rect x='-77' y='-141' width='154' height='282' rx='22'/></clipPath>
  <g clip-path='url(#pantalla)'>
    <rect x='-77' y='-141' width='154' height='282' fill='url(#gPantalla)'/>
    <rect x='-77' y='-141' width='154' height='36' fill='#0a1330'/>
    <image href='{logo}' x='-69' y='-133' width='22' height='22'/>
    <g transform='translate(-43 -126) scale(.105)'>{nombre}</g>
    <rect x='12' y='-131' width='57' height='18' rx='6' fill='#2f6bff'/>
    <path d='{trazos("negrita", "Iniciar sesión", 7.4, 40.5, -119, "centro")}' fill='#fff'/>
    <g transform='translate(0 0)'>{pa}{pb}{pc}</g>
    <path class='reflejo' d='M-100 -141H-60L-120 141H-160Z' fill='url(#gHaz)'/>
  </g>
  <rect x='-22' y='-146' width='44' height='6' rx='3' fill='#070c1c'/>
</g></g>"""

    return f"""<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 {ANCHO} {ALTO}' width='{ANCHO}' height='{ALTO}' role='img'>
<title>FFmovil: somos distribuidor de Free Fire</title>
<style>{CSS}</style>
<defs>
<linearGradient id='gFondo' x1='0' y1='0' x2='1' y2='0'><stop offset='0' stop-color='#040815'/><stop offset='.5' stop-color='#071331'/><stop offset='1' stop-color='#0a1f55'/></linearGradient>
<linearGradient id='gPanel' x1='0' y1='0' x2='1' y2='1'><stop offset='0' stop-color='#1237a8' stop-opacity='.9'/><stop offset='.55' stop-color='#0c2470' stop-opacity='.85'/><stop offset='1' stop-color='#071538' stop-opacity='.95'/></linearGradient>
<linearGradient id='gTitulo' x1='0' y1='0' x2='0' y2='1'><stop offset='0' stop-color='#9cc8ff'/><stop offset='.5' stop-color='#3f7dff'/><stop offset='1' stop-color='#1f4fe0'/></linearGradient>
<linearGradient id='gBorde' x1='0' y1='0' x2='0' y2='1'><stop offset='0' stop-color='#8fb0ff' stop-opacity='0'/><stop offset='.5' stop-color='#8fb0ff' stop-opacity='.9'/><stop offset='1' stop-color='#8fb0ff' stop-opacity='0'/></linearGradient>
<linearGradient id='gPantalla' x1='0' y1='0' x2='0' y2='1'><stop offset='0' stop-color='#0c1a48'/><stop offset='1' stop-color='#061030'/></linearGradient>
<linearGradient id='gHaz' x1='0' y1='0' x2='1' y2='0'><stop offset='0' stop-color='#fff' stop-opacity='0'/><stop offset='.5' stop-color='#fff' stop-opacity='.55'/><stop offset='1' stop-color='#fff' stop-opacity='0'/></linearGradient>
<linearGradient id='gBoton' x1='0' y1='0' x2='0' y2='1'><stop offset='0' stop-color='#3a74ff'/><stop offset='1' stop-color='#2559d6'/></linearGradient>
<radialGradient id='gResplandor' cx='.5' cy='.5' r='.5'><stop offset='0' stop-color='#3f86ff' stop-opacity='.55'/><stop offset='1' stop-color='#3f86ff' stop-opacity='0'/></radialGradient>
<linearGradient id='gSuelo' x1='0' y1='1' x2='0' y2='0'><stop offset='0' stop-color='#2f6bff' stop-opacity='.35'/><stop offset='1' stop-color='#2f6bff' stop-opacity='0'/></linearGradient>
<clipPath id='recorte'><rect width='{ANCHO}' height='{ALTO}'/></clipPath>
<linearGradient id='gTarjeta' x1='0' y1='0' x2='0' y2='1'><stop offset='0' stop-color='#1b3fb8'/><stop offset='.6' stop-color='#2859e0'/><stop offset='1' stop-color='#5f90ff'/></linearGradient>
<pattern id='puntos' width='4' height='4' patternUnits='userSpaceOnUse'><circle cx='2' cy='2' r='.55' fill='#fff' fill-opacity='.16'/></pattern>
<clipPath id='recTarjeta'><rect x='-71' y='-101' width='142' height='238' rx='13'/></clipPath>
<pattern id='puntosFondo' width='14' height='14' patternUnits='userSpaceOnUse'><circle cx='7' cy='7' r='.9' fill='#6aa5ff' fill-opacity='.35'/></pattern>
<linearGradient id='gFadeIzq' x1='0' y1='0' x2='1' y2='0'><stop offset='0' stop-color='#fff'/><stop offset='1' stop-color='#000'/></linearGradient>
<mask id='mIzq'><rect width='520' height='{ALTO}' fill='url(#gFadeIzq)'/></mask>
<radialGradient id='gResplandorIzq' cx='.5' cy='.5' r='.5'><stop offset='0' stop-color='#2f6bff' stop-opacity='.22'/><stop offset='1' stop-color='#2f6bff' stop-opacity='0'/></radialGradient>
<clipPath id='recTitulo'><path d='{distrib}'/></clipPath>
<clipPath id='recBoton'><rect x='104' y='258' width='222' height='48' rx='13'/></clipPath>
<clipPath id='recPanel'><path d='M575 0H995V340H492Z'/></clipPath>
<filter id='brillo' x='-20%' y='-20%' width='140%' height='140%'><feGaussianBlur stdDeviation='6'/></filter>
<filter id='sombra' x='-30%' y='-30%' width='160%' height='160%'><feDropShadow dx='0' dy='4' stdDeviation='5' flood-color='#02060f' flood-opacity='.7'/></filter>
{defs_simbolos}
</defs>

<g clip-path='url(#recorte)'>
  <rect width='{ANCHO}' height='{ALTO}' fill='url(#gFondo)'/>
  <rect y='200' width='{ANCHO}' height='140' fill='url(#gSuelo)'/>
  <rect width='520' height='{ALTO}' fill='url(#puntosFondo)' mask='url(#mIzq)' class='rejilla-r'/>
  <ellipse cx='250' cy='150' rx='300' ry='110' fill='url(#gResplandorIzq)'/>
  <g>{trazos_de_circuito()}</g>
  <g>{usos_simbolos}</g>

  <!-- panel derecho con borde diagonal -->
  <path d='M575 0H995V340H492Z' fill='url(#gPanel)'/>
  <g clip-path='url(#recPanel)'>
    <ellipse cx='820' cy='190' rx='240' ry='190' fill='url(#gResplandor)'/>
    <g class='haz'><path d='M560 0H610L440 340H390Z' fill='#fff' opacity='.08'/><path d='M640 0H655L505 340H490Z' fill='#fff' opacity='.1'/></g>
  </g>
  <path d='M575 0L492 340' stroke='url(#gBorde)' stroke-width='2' fill='none'/>

  <!-- gemas que suben y destellos -->
  {gemas}
  {chispas}

  <!-- texto de la izquierda -->
  <g class='entra-izq'>
    <image href='{ff_grande[0]}' x='36' y='26' width='168' height='{ff_alto}'/>
  </g>
  <g class='entra-izq' style='animation-delay:.12s'>
    <path d='{somos}' fill='#fff'/>
  </g>
  <g class='entra-izq' style='animation-delay:.24s'>
    <path d='{distrib}' fill='#1a46c8' opacity='.55' transform='translate(0 4)'/>
    <path d='{distrib}' fill='url(#gTitulo)'/>
    <g clip-path='url(#recTitulo)'><g class='barre-t'><path d='M30 150h70l-40 62h-70z' fill='url(#gHaz)'/></g></g>
  </g>

  <!-- personajes y cofre -->
  <g class='entra-der' style='animation-delay:.3s'><g class='flota2' filter='url(#sombra)'>
    <image href='{pj1[0]}' x='655' y='{ALTO - round(pj1[2] * 253 / pj1[1]) + 4}' width='253' height='{round(pj1[2] * 253 / pj1[1])}'/>
  </g></g>
  <g class='entra-der' style='animation-delay:.2s'>{celular}</g>
  <g class='entra-arr' style='animation-delay:.55s'><g class='flota3' filter='url(#sombra)'>
    <image href='{cofre[0]}' x='578' y='{ALTO - round(cofre[2] * 138 / cofre[1]) - 4}' width='138' height='{round(cofre[2] * 138 / cofre[1])}'/>
  </g></g>
  <g class='entra-der' style='animation-delay:.4s'><g class='flota' filter='url(#sombra)'>
    <image href='{pj3[0]}' x='763' y='{ALTO - round(pj3[2] * 236 / pj3[1]) + 6}' width='236' height='{round(pj3[2] * 236 / pj3[1])}'/>
  </g></g>
  <g class='entra-arr' style='animation-delay:.7s'><g class='flota3'>
    <image href='{dia_g[0]}' x='700' y='14' width='64' height='{round(dia_g[2] * 64 / dia_g[1])}' transform='rotate(-12 732 30)'/>
  </g></g>

  <!-- botón y pie -->
  <g class='entra-arr' style='animation-delay:.5s'>
    <image href='{logo}' x='35' y='251' width='62' height='62'/>
    <g class='pulso' style='transform-origin:215px 282px'>
      <rect x='104' y='258' width='222' height='48' rx='13' fill='url(#gBoton)'/>
      <g clip-path='url(#recBoton)'><g class='destello-b'><path d='M104 258h26l-18 48h-26z' fill='#fff' opacity='.28' transform='translate(0 0)'/></g></g>
      <path d='{boton_txt}' fill='#fff'/>
      <g class='flecha'><path d='M287 282h22M300 272l11 10l-11 10' fill='none' stroke='#fff' stroke-width='3.4' stroke-linecap='round' stroke-linejoin='round'/></g>
    </g>
    <path d='{sub}' fill='#c9d6f7'/>
  </g>
</g>
</svg>"""


def codificar_url(svg: str) -> str:
    """Valor para Dhru: url("data:image/svg+xml,...") con solo lo imprescindible codificado."""
    s = re.sub(r">\s+<", "><", svg.strip())
    s = s.replace("\n", " ")
    for a, b in (("%", "%25"), ("#", "%23"), ("<", "%3C"), (">", "%3E"), ('"', "%22")):
        s = s.replace(a, b)
    return f'url("data:image/svg+xml,{s}")'


def principal() -> None:
    SALIDA.mkdir(exist_ok=True)
    svg = construir()
    svg = re.sub(r">\s+<", "><", svg)
    (SALIDA / "banner.svg").write_text(svg)
    (SALIDA / "banner-dhru.txt").write_text(codificar_url(svg))
    b64 = base64.b64encode(svg.encode()).decode()
    (SALIDA / "banner-dhru-b64.txt").write_text(f'url("data:image/svg+xml;base64,{b64}")')
    for n in ("banner.svg", "banner-dhru.txt", "banner-dhru-b64.txt"):
        print(f"{n}: {(SALIDA / n).stat().st_size / 1024:.0f} KB")


if __name__ == "__main__":
    principal()
