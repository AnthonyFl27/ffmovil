"""Flujo de recarga: validación, reserva, llamada al proveedor y resolución (plan sec. 4).

Los mensajes de las excepciones están en español y pueden mostrarse al cliente.
"""

import logging
import re
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Paquete
from app.services.ventasff_client import ClienteVentasFF, ErrorVentasFF

logger = logging.getLogger(__name__)

# RF-27: Player ID numérico de 4 a 20 dígitos.
PATRON_PLAYER_ID = re.compile(r"[0-9]{4,20}")

ADVERTENCIA_NO_DISPONIBLE = (
    "No se pudo verificar el ID en este momento. Revisa que sea correcto antes de confirmar."
)


class ErrorRecarga(Exception):
    """Recarga rechazada antes de reservar saldo."""


class PlayerIdInvalido(ErrorRecarga):
    pass


class JugadorNoExiste(ErrorRecarga):
    pass


class PaqueteNoDisponible(ErrorRecarga):
    pass


@dataclass(frozen=True)
class ResultadoValidacion:
    # ok | no_disponible | error_validador
    estado: str
    nickname: str | None
    # Texto para el cliente cuando el ID no pudo verificarse (RF-20).
    advertencia: str | None = None

    @property
    def verificado(self) -> bool:
        return self.estado == "ok"


def validar_formato_player_id(player_id: str) -> str:
    """Devuelve el Player ID sin espacios alrededor o lanza `PlayerIdInvalido` (RF-27)."""
    if not isinstance(player_id, str) or not PATRON_PLAYER_ID.fullmatch(player_id.strip()):
        raise PlayerIdInvalido("El Player ID debe tener solo números, de 4 a 20 dígitos")
    return player_id.strip()


async def paquete_disponible(sesion: AsyncSession, paquete_id: int) -> Paquete:
    """Paquete activo y con precio de venta (RF-13); si no, `PaqueteNoDisponible`."""
    paquete = await sesion.scalar(
        select(Paquete).where(Paquete.paquete_id == paquete_id, Paquete.activo.is_(True))
    )
    if paquete is None or paquete.precio_venta is None:
        raise PaqueteNoDisponible("El paquete no está disponible")
    return paquete


async def validar_jugador(
    sesion: AsyncSession, cliente: ClienteVentasFF, player_id: str, paquete_id: int
) -> ResultadoValidacion:
    """Valida el Player ID con `validar.php` y devuelve el nickname (RF-20, RF-26, RF-27).

    - `no_existe` → `JugadorNoExiste`: la recarga se bloquea.
    - `no_disponible` o fallo del validador → se advierte y se permite continuar
      bajo confirmación del cliente.
    """
    player_id = validar_formato_player_id(player_id)
    await paquete_disponible(sesion, paquete_id)
    try:
        validacion = await cliente.validar(player_id, paquete_id)
    except ErrorVentasFF as error:
        logger.warning("validar.php falló: %s", type(error).__name__)
        return ResultadoValidacion("error_validador", None, ADVERTENCIA_NO_DISPONIBLE)

    if validacion.estado == "no_existe":
        raise JugadorNoExiste("El Player ID no existe en Free Fire")
    if validacion.estado == "ok":
        return ResultadoValidacion("ok", validacion.nickname)
    if validacion.estado != "no_disponible":
        logger.warning("validar.php devolvió un estado desconocido: %r", validacion.estado)
        return ResultadoValidacion("error_validador", None, ADVERTENCIA_NO_DISPONIBLE)
    return ResultadoValidacion("no_disponible", None, ADVERTENCIA_NO_DISPONIBLE)
