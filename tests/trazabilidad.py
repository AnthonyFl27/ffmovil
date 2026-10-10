"""Trazabilidad de requisitos (T-083): RF/RN/RNF/CA → tareas y pruebas.

Fuentes (solo lectura, sin BD ni red):
- `sdd/spec.md`: requisitos definidos (`- **RF-01** …`); los marcados `(retirado` se omiten.
- `sdd/tasks.md`: cada tarea cita los requisitos que cubre (admite rangos "RF-50 a RF-55").
- `tests/test_*.py`: una prueba cubre un requisito si lo nombra (docstring o comentario).

Uso: `uv run python -m tests.trazabilidad` imprime la tabla en Markdown y sale con
código 1 si algún requisito no tiene tarea o prueba y no está en `SIN_PRUEBA_AUTOMATICA`.
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
PREFIJOS = r"RNF|RF|RN|CA"
ID = rf"(?:{PREFIJOS})-\d+"
RE_DEFINICION = re.compile(rf"^\s*- \*\*({ID})\*\*(.*)$")
RE_TAREA = re.compile(r"^- \[[ x~!]\] (T-\d+)\b(.*)$")
RE_RANGO = re.compile(rf"\b({PREFIJOS})-(\d+) a (?:\1-)?(\d+)\b")
RE_ID = re.compile(rf"\b({ID})\b")

# Requisitos que no admiten una prueba automatizada: se verifican por revisión.
# Cada uno lleva el motivo; añadir uno aquí exige justificarlo.
SIN_PRUEBA_AUTOMATICA = {
    "RNF-06": "repositorio público sin secretos: revisión previa a cada push (AGENTS.md)",
    "RNF-07": "BD externa por DATABASE_URL: se verifica con el Compose y toda la suite contra el VPS",
}

# Tareas de proceso o decisión (T-070 resuelve Q-05) que no implementan un requisito.
TAREAS_SIN_REQUISITO = {"T-070", "T-083"}


@dataclass
class Fila:
    requisito: str
    tareas: set[str] = field(default_factory=set)
    pruebas: set[str] = field(default_factory=set)


def ids_en(texto: str) -> set[str]:
    """IDs citados en un texto, con los rangos `RF-50 a RF-55` expandidos."""
    ids = set(RE_ID.findall(texto))
    for prefijo, ini, fin in RE_RANGO.findall(texto):
        for n in range(int(ini), int(fin) + 1):
            ids.add(f"{prefijo}-{n:02d}")
    return ids


def requisitos_de_la_spec(raiz: Path = RAIZ) -> list[str]:
    ids: list[str] = []
    for linea in (raiz / "sdd" / "spec.md").read_text(encoding="utf-8").splitlines():
        m = RE_DEFINICION.match(linea)
        if m and "(retirado" not in m.group(2):
            ids.append(m.group(1))
    return ids


def tareas_del_plan(raiz: Path = RAIZ) -> dict[str, set[str]]:
    """Mapa tarea → requisitos que cita (en cualquier parte de su línea)."""
    tareas: dict[str, set[str]] = {}
    for linea in (raiz / "sdd" / "tasks.md").read_text(encoding="utf-8").splitlines():
        m = RE_TAREA.match(linea)
        if m:
            tareas[m.group(1)] = ids_en(linea)
    return tareas


def pruebas_por_requisito(raiz: Path = RAIZ) -> dict[str, set[str]]:
    """Mapa requisito → archivos de prueba que lo nombran."""
    mapa: dict[str, set[str]] = {}
    for archivo in sorted((raiz / "tests").glob("test_*.py")):
        if archivo.name == "test_trazabilidad.py":
            continue
        for req in ids_en(archivo.read_text(encoding="utf-8")):
            mapa.setdefault(req, set()).add(archivo.name)
    return mapa


def construir(raiz: Path = RAIZ) -> list[Fila]:
    tareas = tareas_del_plan(raiz)
    pruebas = pruebas_por_requisito(raiz)
    filas = []
    for req in requisitos_de_la_spec(raiz):
        fila = Fila(req)
        fila.tareas = {t for t, citados in tareas.items() if req in citados}
        fila.pruebas = pruebas.get(req, set())
        filas.append(fila)
    return filas


def problemas(raiz: Path = RAIZ) -> list[str]:
    """Huecos de trazabilidad; lista vacía = todo cubierto."""
    lista = []
    for fila in construir(raiz):
        if not fila.tareas:
            lista.append(f"{fila.requisito}: sin tarea en sdd/tasks.md")
        if not fila.pruebas and fila.requisito not in SIN_PRUEBA_AUTOMATICA:
            lista.append(f"{fila.requisito}: sin prueba que lo nombre en tests/")
    spec = set(requisitos_de_la_spec(raiz))
    for tarea, citados in tareas_del_plan(raiz).items():
        if not citados and tarea not in TAREAS_SIN_REQUISITO:
            lista.append(f"{tarea}: la tarea no cita ningún requisito")
        for req in sorted(citados - spec):
            lista.append(f"{tarea}: cita {req}, que no existe en la spec (o está retirado)")
    return lista


def tabla(raiz: Path = RAIZ) -> str:
    filas = ["| Requisito | Tareas | Pruebas |", "|---|---|---|"]
    for f in construir(raiz):
        tareas = ", ".join(sorted(f.tareas)) or "—"
        if f.pruebas:
            pruebas = ", ".join(sorted(f.pruebas))
        elif f.requisito in SIN_PRUEBA_AUTOMATICA:
            pruebas = f"revisión: {SIN_PRUEBA_AUTOMATICA[f.requisito]}"
        else:
            pruebas = "—"
        filas.append(f"| {f.requisito} | {tareas} | {pruebas} |")
    return "\n".join(filas)


if __name__ == "__main__":
    print(tabla())
    huecos = problemas()
    for h in huecos:
        print(f"HUECO: {h}", file=sys.stderr)
    sys.exit(1 if huecos else 0)
