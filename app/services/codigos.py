"""Código legible de pedido (`FF-000123`), derivado del id numérico de la BD.

La unicidad la garantiza el id y una restricción UNIQUE en la tabla de pedidos;
este módulo es puro y no consulta la base de datos.
"""

import re

PREFIJO = "FF-"
DIGITOS_MINIMOS = 6

_PATRON_CODIGO = re.compile(rf"{re.escape(PREFIJO)}[0-9]{{{DIGITOS_MINIMOS},}}")


def codigo_pedido(pedido_id: int) -> str:
    """Devuelve el código del pedido, con el id rellenado con ceros a 6 dígitos como mínimo.

    Los ids con más dígitos no se truncan (1234567 -> "FF-1234567").

    Lanza ValueError si el id no es un entero positivo (bool no cuenta como entero).
    """
    if isinstance(pedido_id, bool) or not isinstance(pedido_id, int):
        raise ValueError("El id de pedido debe ser un entero")  # noqa: TRY004  # contrato: ValueError, no TypeError
    if pedido_id < 1:
        raise ValueError("El id de pedido debe ser mayor o igual a 1")
    return f"{PREFIJO}{pedido_id:0{DIGITOS_MINIMOS}d}"


def id_desde_codigo(codigo: str) -> int | None:
    """Devuelve el id numérico del código de pedido, o None si el código no es válido.

    Acepta espacios alrededor y prefijo en minúsculas. Solo acepta la forma canónica:
    el código debe ser exactamente igual a codigo_pedido(id) tras normalizarlo.
    Nunca lanza excepciones por entradas incorrectas.
    """
    if not isinstance(codigo, str):
        return None
    normalizado = codigo.strip().upper()
    if _PATRON_CODIGO.fullmatch(normalizado) is None:
        return None
    pedido_id = int(normalizado[len(PREFIJO) :])
    if pedido_id < 1:
        return None
    if codigo_pedido(pedido_id) != normalizado:
        return None
    return pedido_id
