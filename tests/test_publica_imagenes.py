"""T-121: imágenes de las páginas públicas ligeras y accesibles (RNF-20, RF-58).

Cada imagen pesa a lo sumo 150 KB y todas juntas a lo sumo 800 KB; cada `<img>`
de las plantillas públicas lleva `width`, `height` y `alt`.
"""

import re
from pathlib import Path

import pytest

from app.web.plantillas import DIRECTORIO_ESTATICOS, DIRECTORIO_PLANTILLAS

TOPE_IMAGEN = 150 * 1024
TOPE_TOTAL = 800 * 1024
PLANTILLAS = sorted((DIRECTORIO_PLANTILLAS / "publica").glob("*.html"))
IMG = re.compile(r"<img\b[^>]*>", re.IGNORECASE)
ESTATICO = re.compile(r"""estatico\(["']([^"']+)["']\)""")


def _imagenes_usadas() -> set[Path]:
    """Imágenes de `app/static` que enlazan las plantillas públicas (incluye el sello)."""
    usadas = set()
    for plantilla in PLANTILLAS:
        for etiqueta in IMG.findall(plantilla.read_text()):
            usadas.update(DIRECTORIO_ESTATICOS / n for n in ESTATICO.findall(etiqueta))
    return usadas


def test_las_imagenes_de_inicio_son_webp():
    nombres = {p.name for p in (DIRECTORIO_ESTATICOS / "inicio").iterdir()}
    assert nombres and all(n.endswith(".webp") for n in nombres)


@pytest.mark.parametrize("imagen", sorted((DIRECTORIO_ESTATICOS / "inicio").glob("*")), ids=str)
def test_cada_imagen_pesa_a_lo_sumo_150_kb(imagen):
    """RNF-20: tope por imagen."""
    assert imagen.stat().st_size <= TOPE_IMAGEN


def test_las_imagenes_publicas_juntas_pesan_a_lo_sumo_800_kb():
    """RNF-20: tope total, contando también las imágenes fuera de `inicio/` (sello)."""
    usadas = _imagenes_usadas() | set((DIRECTORIO_ESTATICOS / "inicio").glob("*"))
    assert all(p.exists() for p in usadas)
    assert all(p.stat().st_size <= TOPE_IMAGEN for p in usadas)
    assert sum(p.stat().st_size for p in usadas) <= TOPE_TOTAL


@pytest.mark.parametrize("plantilla", PLANTILLAS, ids=lambda p: p.name)
def test_cada_img_lleva_width_height_y_alt(plantilla):
    """RNF-20: dimensiones (sin saltos al cargar) y texto alternativo en cada imagen."""
    for etiqueta in IMG.findall(plantilla.read_text()):
        for atributo in ("width", "height", "alt"):
            assert re.search(rf'\s{atributo}="[^"]*"', etiqueta), (atributo, etiqueta)
