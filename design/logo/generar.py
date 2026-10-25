"""Genera los SVG y PNG del logo de FFmovil. Fuente única: este archivo.

Uso (desde la raíz del repo; solo biblioteca estándar, los PNG usan ImageMagick con librsvg):

    python3 design/logo/generar.py

Los archivos se escriben en design/logo/svg/ y design/logo/png/. No toca app/static/.
Geometría y reglas de diseño: design/logo/README.md.
"""

import shutil
import subprocess
from pathlib import Path

RAIZ = Path(__file__).parent
SVG = RAIZ / "svg"
PNG = RAIZ / "png"

# Ícono «ff en cursiva» (propuesta G, elegida por el dueño el 2026-10-24 a partir de su boceto):
# dos F inclinadas 1:2 (unos 27°) y un rombo facetado. La barra de la F delantera cruza el
# tronco de la trasera; ahí la trasera se recorta con el espacio de 4 (máscara). Lienzo
# 108 x 100; el conjunto ocupa x 4–104, y 10–90. Trazo 13 (troncos) y 12 (barras).
ANCHO, ALTO = 108, 100
CENTRO = (54, 50)  # centro del conjunto, para centrarlo en el cuadrado de app


def _tallo(x_sup: float, y0: float, y1: float, ancho: float) -> str:
    """Tronco inclinado: borde izquierdo en x_sup arriba (y0); baja 1 en x por cada 2 en y."""
    dx = (y1 - y0) / 2
    return f"M{x_sup} {y0}H{x_sup + ancho}L{x_sup + ancho - dx} {y1}H{x_sup - dx}Z"


def _barra(x_izq: float, x_der: float, y0: float, alto: float) -> str:
    """Barra horizontal con los extremos cortados en la misma inclinación que los troncos."""
    dx = alto / 2
    return f"M{x_izq} {y0}H{x_der}L{x_der - dx} {y0 + alto}H{x_izq - dx}Z"


def _rombo(cx: float, cy: float, r: float, mesa: float) -> list[str]:
    """Rombo de semidiagonal r: 4 facetas (arriba-izquierda, arriba-derecha, abajo-derecha,
    abajo-izquierda) alrededor de una mesa central de semidiagonal `mesa`."""
    i, d, a, b = cx - r, cx + r, cy - r, cy + r
    mi, md, ma, mb = cx - mesa, cx + mesa, cy - mesa, cy + mesa
    return [
        f"M{i} {cy}L{cx} {a}V{ma}L{mi} {cy}Z",
        f"M{cx} {a}L{d} {cy}H{md}L{cx} {ma}Z",
        f"M{d} {cy}L{cx} {b}V{mb}L{md} {cy}Z",
        f"M{cx} {b}L{i} {cy}H{mi}L{cx} {mb}Z",
        f"M{mi} {cy}L{cx} {ma}L{md} {cy}L{cx} {mb}Z",
    ]


F_TRASERA = [_tallo(44, 10, 90, 13), _barra(34, 104, 10, 12)]
F_DELANTERA = [_tallo(54, 32, 90, 13), _barra(14, 80, 32, 12)]
BARRA_CRUZA = F_DELANTERA[1]
ROMBO = _rombo(77, 67, 19, 8)

# Contraste mínimo de las F contra cada fondo de su variante (WCAG 1.4.11, gráficos).
CONTRASTE_MIN = 3.0

# Colores por variante; luz desde arriba a la izquierda. Facetas en el orden de _rombo.
VARIANTES = {
    # Para fondos oscuros (la web pública usa #0a1128; las tarjetas, #111c3d).
    "oscuro": {
        "fondos": ["#0a1128", "#111c3d"],
        "trasera": "#4068da",
        "delantera": "#5a90ff",
        "facetas": ["#c4e9ff", "#7cc4ff", "#2160dc", "#3b8ff5", "#9ddcff"],
    },
    # Para fondos claros: la F trasera más clara que la delantera, pero ≥ 3:1 sobre blanco.
    "claro": {
        "fondos": ["#ffffff"],
        "trasera": "#6a8ce8",
        "delantera": "#1f4fd6",
        "facetas": ["#3a98ec", "#2a85ec", "#0c3a9e", "#1a63d8", "#8fd3ff"],
    },
}

FONDO_APP = "#111c3d"
BORDE_APP = "#25346b"
# Proporción del ícono dentro del cuadrado de app.
ESCALA_APP = 0.84
# El favicon (sin borde) aprovecha más el cuadrado: a 32 px cada punto cuenta.
ESCALA_FAVICON = 0.92

# Letras del nombre, en la misma cuadrícula que el ícono: base en y = 90, altura x 44
# (y = 46), ascendentes hasta y = 10 (la altura de las F), trazo 12 y chaflanes a 45°
# (12 por fuera, 5 por dentro, para que el trazo diagonal también mida 12).
# (avance, trazado); los huecos se recortan con fill-rule="evenodd". El gancho de la «f»
# llega a x = 36 pero avanza 30 (lo que mide su barra): sobresale sobre el espacio siguiente.
LETRAS = {
    "m": (56, "M0 46H44L56 58V90H44V63L39 58H34V90H22V63L17 58H12V90H0Z"),
    "o": (40, "M12 46H28L40 58V78L28 90H12L0 78V58Z M17 58H23L28 63V73L23 78H17L12 73V63Z"),
    "v": (40, "M0 46H12V67L20 75L28 67V46H40V72L22 90H18L0 72Z"),
    "i": (12, "M0 46H12V90H0Z"),
    "l": (12, "M0 10H12V90H0Z"),
    "f": (30, "M0 46H6V24L20 10H36V22H25L18 29V46H30V58H18V90H6V58H0Z"),
}
ESPACIO_LETRAS = 8
# Punto de la «i»: gema diminuta de 16 x 12 (corona y pabellón a 45°), 4 por encima del trazo.
# Facetas: corona izquierda y derecha, pabellón izquierdo y derecho (luz arriba a la izquierda).
PUNTO_GEMA = [
    "M-2 34L2 30H6V34Z",
    "M6 30H10L14 34H6Z",
    "M-2 34H6V42Z",
    "M6 34H14L6 42Z",
]
COLORES_PUNTO = {
    "oscuro": ["#c4e9ff", "#4aa8ff", "#5cb8ff", "#2563e2"],
    "claro": ["#6cc4ff", "#1f6fe0", "#2a85ec", "#0c3a9e"],
}
TEXTO = {"oscuro": "#ffffff", "claro": "#0a1128"}


def _p(trazados: list[str], relleno: str) -> str:
    return "".join(f'<path d="{d}" fill="{relleno}"/>' for d in trazados)


def _cuerpo(variante: str) -> str:
    """Las piezas del ícono, de atrás hacia delante, con el hueco del cruce."""
    v = VARIANTES[variante]
    return (
        f'<mask id="cruce" maskUnits="userSpaceOnUse" x="0" y="0" width="{ANCHO}" height="{ALTO}">'
        f'<rect width="{ANCHO}" height="{ALTO}" fill="#fff"/>'
        f'<path d="{BARRA_CRUZA}" fill="#000" stroke="#000" stroke-width="8"/></mask>'
        f'<g mask="url(#cruce)">{_p(F_TRASERA, v["trasera"])}</g>'
        + _p(F_DELANTERA, v["delantera"])
        + "".join(f'<path d="{d}" fill="{c}"/>' for d, c in zip(ROMBO, v["facetas"], strict=True))
    )


def _nombre(texto: str, x0: float, variante: str) -> tuple[str, float]:
    """Trazos del nombre a partir de x0; devuelve (svg, x final)."""
    partes, x = [], x0
    for letra in texto:
        ancho, d = LETRAS[letra]
        partes.append(
            f'<path transform="translate({x} 0)" fill-rule="evenodd" d="{d}" fill="{TEXTO[variante]}"/>'
        )
        if letra == "i":
            partes.extend(
                f'<path transform="translate({x} 0)" d="{d}" fill="{c}"/>'
                for d, c in zip(PUNTO_GEMA, COLORES_PUNTO[variante], strict=True)
            )
        x += ancho + ESPACIO_LETRAS
    return "".join(partes), x - ESPACIO_LETRAS


def icono(variante: str) -> str:
    """Ícono con fondo transparente (108 x 100)."""
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {ANCHO} {ALTO}" '
        f'width="{ANCHO * 4}" height="{ALTO * 4}" role="img">'
        f"<title>FFmovil</title>{_cuerpo(variante)}</svg>"
    )


def _centrado(escala: float) -> str:
    x, y = 50 - CENTRO[0] * escala, 50 - CENTRO[1] * escala
    return f'<g transform="translate({x:.2f} {y:.2f}) scale({escala})">{_cuerpo("oscuro")}</g>'


def app(redondeado: bool) -> str:
    """Ícono de app cuadrado (100 x 100): el ícono centrado sobre un azul marino.

    redondeado=False es el cuadrado a sangre que pide apple-touch-icon (iOS redondea solo).
    """
    if redondeado:
        fondo = (
            f'<rect x="1" y="1" width="98" height="98" rx="22" fill="{FONDO_APP}" '
            f'stroke="{BORDE_APP}" stroke-width="1.5"/>'
        )
    else:
        fondo = f'<rect width="100" height="100" fill="{FONDO_APP}"/>'
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100" width="512" height="512" role="img">'
        f"<title>FFmovil</title>{fondo}{_centrado(ESCALA_APP)}</svg>"
    )


def favicon() -> str:
    """Favicon (32 x 32): el mismo ícono más grande y sin borde, que a 32 px se vuelve un halo."""
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100" width="32" height="32" role="img">'
        f'<title>FFmovil</title><rect width="100" height="100" rx="20" fill="{FONDO_APP}"/>'
        f"{_centrado(ESCALA_FAVICON)}</svg>"
    )


def nombre_svg(variante: str) -> str:
    """Nombre «ffmovil» (elegido por el dueño el 2026-10-24), recortado a sus trazos: de la
    ascendente (y = 10) a la base (y = 90). Va junto al ícono, que pone la marca gráfica."""
    trazos, fin = _nombre("ffmovil", 0, variante)
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 10 {fin} 80" '
        f'width="{fin * 3}" height="240" role="img"><title>FFmovil</title>{trazos}</svg>'
    )


def _luminancia(color: str) -> float:
    canales = [int(color[i : i + 2], 16) / 255 for i in (1, 3, 5)]
    r, g, b = (c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in canales)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def _contraste(a: str, b: str) -> float:
    la, lb = sorted((_luminancia(a), _luminancia(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def revisar_contraste() -> None:
    """Imprime el peor contraste de las F contra cada fondo de su variante."""
    for nombre, v in VARIANTES.items():
        for fondo in v["fondos"]:
            peor = min((v["trasera"], v["delantera"]), key=lambda c, f=fondo: _contraste(c, f))
            valor = _contraste(peor, fondo)
            aviso = "" if valor >= CONTRASTE_MIN else f"  <-- por debajo de {CONTRASTE_MIN}:1"
            print(f"Contraste {nombre} sobre {fondo}: {valor:.2f}:1 (peor: {peor}){aviso}")


def escribir_svg() -> dict[str, Path]:
    SVG.mkdir(parents=True, exist_ok=True)
    archivos = {
        "ffmovil-icono": icono("oscuro"),
        "ffmovil-icono-claro": icono("claro"),
        "ffmovil-app": app(True),
        "ffmovil-app-cuadrado": app(False),
        "ffmovil-favicon": favicon(),
        "ffmovil-nombre": nombre_svg("oscuro"),
        "ffmovil-nombre-claro": nombre_svg("claro"),
    }
    rutas = {}
    for nombre, contenido in archivos.items():
        ruta = SVG / f"{nombre}.svg"
        ruta.write_text(contenido + "\n", encoding="utf-8")
        rutas[nombre] = ruta
    return rutas


# (svg de origen, png de salida, lado en px o None para fijar solo el alto, alto en px)
EXPORTACIONES = [
    ("ffmovil-icono", "ffmovil-icono-512.png", None, 512),
    ("ffmovil-icono-claro", "ffmovil-icono-claro-512.png", None, 512),
    ("ffmovil-app", "logo-192.png", 192, 192),
    ("ffmovil-favicon", "favicon-32.png", 32, 32),
    ("ffmovil-app-cuadrado", "apple-touch-icon-180.png", 180, 180),
    ("ffmovil-app", "ffmovil-app-512.png", 512, 512),
    ("ffmovil-nombre", "ffmovil-nombre-240.png", None, 240),
    ("ffmovil-nombre-claro", "ffmovil-nombre-claro-240.png", None, 240),
]


def exportar_png(rutas: dict[str, Path]) -> None:
    magick = shutil.which("magick") or shutil.which("convert")
    if not magick:
        print("ImageMagick no está instalado: se omiten los PNG.")
        return
    PNG.mkdir(parents=True, exist_ok=True)
    for origen, salida, lado, alto in EXPORTACIONES:
        destino = PNG / salida
        # -density alta para que librsvg rasterice con nitidez y luego se reduce.
        if lado is None:  # ícono o nombre más anchos que altos: se fija el alto
            medida = ["-resize", f"x{alto}"]
        else:
            medida = ["-resize", f"{lado}x{lado}"]
        subprocess.run(
            [
                magick,
                "-background",
                "none",
                "-density",
                "384",
                str(rutas[origen]),
                *medida,
                "-depth",
                "8",
                str(destino),
            ],
            check=True,
        )
        print("PNG", destino.relative_to(RAIZ))


if __name__ == "__main__":
    rutas = escribir_svg()
    for r in rutas.values():
        print("SVG", r.relative_to(RAIZ))
    exportar_png(rutas)
    revisar_contraste()
