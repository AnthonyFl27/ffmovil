"""Máquina de estados de los pedidos (spec sección 7, RN-04).

Función pura, sin base de datos. Las transiciones de `PENDIENTE_VERIFICAR`
a un estado final solo se permiten con `por_admin=True`.
"""

from collections.abc import Mapping
from enum import StrEnum


class Estado(StrEnum):
    CREADO = "CREADO"
    PROCESANDO = "PROCESANDO"
    EXITOSO = "EXITOSO"
    FALLIDO = "FALLIDO"
    PENDIENTE_VERIFICAR = "PENDIENTE_VERIFICAR"


ESTADOS_FINALES = frozenset({Estado.EXITOSO, Estado.FALLIDO})

ETIQUETAS_CLIENTE: dict[Estado, str] = {
    Estado.CREADO: "Procesando",
    Estado.PROCESANDO: "Procesando",
    Estado.EXITOSO: "Exitoso",
    Estado.FALLIDO: "Fallido",
    Estado.PENDIENTE_VERIFICAR: "En revisión",
}

# Transiciones automáticas permitidas, por estado de origen.
_TRANSICIONES_AUTOMATICAS: Mapping[Estado, frozenset[Estado]] = {
    Estado.CREADO: frozenset({Estado.PROCESANDO}),
    Estado.PROCESANDO: frozenset({Estado.EXITOSO, Estado.FALLIDO, Estado.PENDIENTE_VERIFICAR}),
    Estado.PENDIENTE_VERIFICAR: frozenset(),
    Estado.EXITOSO: frozenset(),
    Estado.FALLIDO: frozenset(),
}

# Transiciones adicionales que solo puede hacer el admin.
_TRANSICIONES_ADMIN: Mapping[Estado, frozenset[Estado]] = {
    Estado.PENDIENTE_VERIFICAR: frozenset({Estado.EXITOSO, Estado.FALLIDO}),
}


class TransicionInvalida(Exception):
    """Transición de estado no permitida.

    `actual` y `nuevo` guardan los valores recibidos (Estado o str).
    """

    def __init__(self, actual: Estado | str, nuevo: Estado | str) -> None:
        self.actual = actual
        self.nuevo = nuevo
        super().__init__(f"Transición de pedido no permitida: {_texto(actual)} -> {_texto(nuevo)}")


def _texto(valor: Estado | str) -> str:
    return valor.value if isinstance(valor, Estado) else str(valor)


def _convertir(valor: Estado | str) -> Estado:
    """Convierte a Estado o lanza `ValueError` si el valor no existe."""
    return Estado(valor)


def transiciones_desde(actual: Estado, *, por_admin: bool = False) -> frozenset[Estado]:
    """Devuelve los estados a los que puede pasar `actual`."""
    permitidas = set(_TRANSICIONES_AUTOMATICAS[actual])
    if por_admin:
        permitidas |= _TRANSICIONES_ADMIN.get(actual, frozenset())
    return frozenset(permitidas)


def validar_transicion(
    actual: Estado | str, nuevo: Estado | str, *, por_admin: bool = False
) -> Estado:
    """Valida el paso de `actual` a `nuevo` y devuelve `nuevo` como Estado.

    Lanza `TransicionInvalida` si el estado no existe o la transición no está
    permitida. `por_admin` solo habilita las transiciones de resolución manual
    desde `PENDIENTE_VERIFICAR`.
    """
    try:
        origen = _convertir(actual)
        destino = _convertir(nuevo)
    except ValueError as error:
        raise TransicionInvalida(actual, nuevo) from error
    if destino not in transiciones_desde(origen, por_admin=por_admin):
        raise TransicionInvalida(actual, nuevo)
    return destino
