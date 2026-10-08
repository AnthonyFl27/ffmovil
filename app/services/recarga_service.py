"""Flujo de recarga: validación, reserva, llamada al proveedor y resolución (plan sec. 4).

Los mensajes de las excepciones están en español y pueden mostrarse al cliente.
"""

import logging
import re
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Paquete, Pedido, PedidoEvento
from app.services import ledger
from app.services.codigos import codigo_pedido
from app.services.estados import Estado, validar_transicion
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


class TokenInvalido(ErrorRecarga):
    pass


class ConfirmacionRequerida(ErrorRecarga):
    """El ID no pudo verificarse: el cliente debe confirmar para continuar (RF-20)."""

    def __init__(self, advertencia: str):
        super().__init__(advertencia)
        self.advertencia = advertencia


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


LARGO_MAXIMO_TOKEN = 200


@dataclass(frozen=True)
class PedidoCreado:
    pedido: Pedido
    # False si el token ya existía y se devolvió el pedido anterior (RF-25).
    nuevo: bool


async def cambiar_estado(
    sesion: AsyncSession,
    pedido: Pedido,
    nuevo: Estado,
    *,
    detalle: str | None = None,
    creado_por: int | None = None,
) -> None:
    """Valida la transición (sec. 7 de la spec), actualiza el pedido y registra el evento.

    `creado_por` es el admin que resuelve; solo así se sale de PENDIENTE_VERIFICAR.
    """
    anterior = pedido.estado
    if anterior is not None:
        validar_transicion(anterior, nuevo, por_admin=creado_por is not None)
    pedido.estado = nuevo
    pedido.actualizado_en = func.now()
    sesion.add(
        PedidoEvento(
            pedido_id=pedido.id,
            estado_anterior=anterior,
            estado_nuevo=nuevo,
            detalle=detalle,
            creado_por=creado_por,
        )
    )
    await sesion.flush()


async def _pedido_por_token(sesion: AsyncSession, usuario_id: int, token: str) -> Pedido | None:
    return await sesion.scalar(
        select(Pedido)
        .where(Pedido.usuario_id == usuario_id, Pedido.token_idempotencia == token)
        .execution_options(populate_existing=True)
    )


async def crear_pedido(
    sesion: AsyncSession,
    cliente: ClienteVentasFF,
    usuario_id: int,
    paquete_id: int,
    player_id: str,
    token_idempotencia: str,
    *,
    confirmar_sin_verificar: bool = False,
) -> PedidoCreado:
    """Fase A (plan 4.2): valida, reserva el saldo y crea el pedido en PROCESANDO.

    Confirma su propia transacción. Un reenvío con el mismo token devuelve el
    pedido existente sin crear otro ni reservar de nuevo (RF-25, CA-02). Si falla,
    no queda pedido ni reserva.
    """
    if (
        not isinstance(token_idempotencia, str)
        or not token_idempotencia.strip()
        or len(token_idempotencia) > LARGO_MAXIMO_TOKEN
    ):
        raise TokenInvalido("Token de idempotencia inválido")

    existente = await _pedido_por_token(sesion, usuario_id, token_idempotencia)
    if existente is not None:
        return PedidoCreado(existente, nuevo=False)

    # RN-03: el ID se valida en el servidor antes de reservar, sin bloqueos tomados.
    validacion = await validar_jugador(sesion, cliente, player_id, paquete_id)
    if not validacion.verificado and not confirmar_sin_verificar:
        raise ConfirmacionRequerida(validacion.advertencia or ADVERTENCIA_NO_DISPONIBLE)
    player_id = validar_formato_player_id(player_id)

    try:
        paquete = await paquete_disponible(sesion, paquete_id)
        # RN-02: precios congelados al crear el pedido.
        pedido = Pedido(
            usuario_id=usuario_id,
            paquete_id=paquete.paquete_id,
            player_id=player_id,
            nickname=validacion.nickname,
            precio_costo=paquete.precio_costo,
            precio_venta=paquete.precio_venta,
            estado=Estado.CREADO,
            token_idempotencia=token_idempotencia,
        )
        sesion.add(pedido)
        try:
            await sesion.flush()
        except IntegrityError as error:
            if "uq_pedidos_usuario_token" not in str(error.orig):
                raise
            # Otro reenvío con el mismo token se adelantó: se devuelve ese pedido.
            await sesion.rollback()
            existente = await _pedido_por_token(sesion, usuario_id, token_idempotencia)
            if existente is None:
                raise
            return PedidoCreado(existente, nuevo=False)

        pedido.codigo = codigo_pedido(pedido.id)
        sesion.add(
            PedidoEvento(pedido_id=pedido.id, estado_anterior=None, estado_nuevo=Estado.CREADO)
        )
        await ledger.reservar(sesion, usuario_id, paquete.precio_venta, pedido_id=pedido.id)
        await cambiar_estado(sesion, pedido, Estado.PROCESANDO, detalle="Saldo reservado")
        await sesion.commit()
    except Exception:
        await sesion.rollback()
        raise
    await sesion.refresh(pedido)
    logger.info("Pedido %s creado y reservado", pedido.codigo)
    return PedidoCreado(pedido, nuevo=True)
