"""Novedades de la plataforma para el equipo admin (RF-63).

Se leen una vez al arrancar de `app/updates.json`; un archivo inválido impide arrancar.
"""

import json
from pathlib import Path

from pydantic import TypeAdapter, ValidationError

from app.schemas.admin import Update

RUTA_UPDATES = Path(__file__).resolve().parent.parent / "updates.json"
_LISTA = TypeAdapter(list[Update])


def cargar_updates(ruta: Path = RUTA_UPDATES) -> list[Update]:
    """Novedades de la más reciente a la más antigua (a igual fecha, el orden del archivo)."""
    try:
        datos = json.loads(ruta.read_text(encoding="utf-8"))
    except OSError:
        raise ValueError(f"No se pudo leer {ruta.name}.") from None
    except json.JSONDecodeError as error:
        raise ValueError(f"{ruta.name} no es JSON válido: {error}") from None
    try:
        lista = _LISTA.validate_python(datos)
    except ValidationError as error:
        problemas = "; ".join(
            f"{'.'.join(str(parte) for parte in detalle['loc'])}: {detalle['msg']}"
            for detalle in error.errors()
        )
        raise ValueError(f"{ruta.name} inválido: {problemas}") from None
    return sorted(lista, key=lambda update: update.fecha, reverse=True)
