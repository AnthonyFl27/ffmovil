"""Lectura de filtros de los formularios web (plan sec. 6.1).

Los formularios envían texto (vacío si no se llenó). Las fechas llegan como día
local (`AAAA-MM-DD`) con el desfase del navegador en minutos (`tz`, como
`Date.getTimezoneOffset()`); se convierten a UTC (RNF-09): `desde` es el inicio
de ese día y `hasta`, el final (exclusivo, inicio del día siguiente).
"""

from datetime import UTC, date, datetime, timedelta
from urllib.parse import urlencode

from fastapi import status

from app.services.estados import Estado
from app.web.plantillas import ErrorWeb

# Desfases horarios reales: de UTC−14 a UTC+14.
DESFASE_MAXIMO_MINUTOS = 14 * 60

MENSAJE_FECHA = "Fecha inválida. Usa el formato AAAA-MM-DD."


def desfase(tz: str | None) -> timedelta:
    try:
        minutos = int(tz or 0)
    except ValueError:
        minutos = 0
    if abs(minutos) > DESFASE_MAXIMO_MINUTOS:
        minutos = 0
    return timedelta(minutes=minutos)


def inicio_dia_utc(dia: str | None, tz: str | None) -> datetime | None:
    """Inicio del día local `dia` expresado en UTC; None si no se indicó."""
    if not dia:
        return None
    try:
        fecha = date.fromisoformat(dia)
    except ValueError:
        raise ErrorWeb(MENSAJE_FECHA, status.HTTP_422_UNPROCESSABLE_CONTENT) from None
    return datetime(fecha.year, fecha.month, fecha.day, tzinfo=UTC) + desfase(tz)


def rango_utc(desde: str | None, hasta: str | None, tz: str | None):
    inicio = inicio_dia_utc(desde, tz)
    fin = inicio_dia_utc(hasta, tz)
    return inicio, fin + timedelta(days=1) if fin is not None else None


def estado(valor: str | None) -> Estado | None:
    try:
        return Estado(valor) if valor else None
    except ValueError:
        return None


def pagina(valor: str | None) -> int:
    try:
        return max(1, int(valor or 1))
    except ValueError:
        return 1


def texto(valor: str | None) -> str | None:
    return valor.strip() or None if valor else None


def consulta(filtros: dict, **cambios) -> str:
    """Querystring con los filtros no vacíos (para la paginación)."""
    return urlencode({k: v for k, v in (filtros | cambios).items() if v not in (None, "")})
