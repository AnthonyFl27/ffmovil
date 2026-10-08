"""Flujo de recarga: validación, reserva, llamada al proveedor y resolución (plan sec. 4).

Los mensajes de las excepciones están en español y pueden mostrarse al cliente.
"""

import asyncio
import logging
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.models import Paquete, Pedido, PedidoEvento
from app.services import ledger
from app.services.codigos import codigo_pedido
from app.services.estados import Estado, validar_transicion
from app.services.limitador import LimitadorTasa
from app.services.ventasff_client import (
    Clasificacion,
    ClienteVentasFF,
    ErrorAPI,
    ErrorPrevioAlEnvio,
    ErrorVentasFF,
    RecargaRealizada,
    ResultadoIncierto,
)

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


# --- Fase B: llamada al proveedor (plan 4.2) ---

# Clave del candado global de recargas: solo una recarga a la vez hacia VentasFF (RN-05).
CANDADO_RECARGAS = 7_461_003
SEGUNDOS_REINTENTO_BUSY = 3.0  # RN-06

ERRORES_DE_CUENTA = frozenset({"MISSING_KEY", "INVALID_KEY", "INACTIVE", "API_DISABLED"})

MENSAJE_SERVICIO_NO_DISPONIBLE = "Servicio no disponible. Intenta más tarde."
MENSAJE_SIN_DISPONIBILIDAD = "Sin disponibilidad del proveedor. Intenta más tarde."
MENSAJE_PROVEEDOR_OCUPADO = "Proveedor ocupado. Intenta más tarde."
MENSAJE_SIN_CONEXION = "No se pudo contactar al proveedor. Intenta más tarde."
MENSAJE_ERROR_RECARGA = "No se pudo completar la recarga."

# Tipos de alerta para el admin (RN-08, T-049).
ALERTA_CREDITO = "credito"
ALERTA_CUENTA = "cuenta"


@dataclass(frozen=True)
class ResultadoProveedor:
    """Resultado de la Fase B, ya clasificado para la Fase C (RF-24)."""

    clasificacion: Clasificacion
    recarga: RecargaRealizada | None = None
    # Motivo para el cliente y código, si el pedido falla.
    motivo: str | None = None
    error_code: str | None = None
    # Alerta para el admin, si corresponde.
    alerta: str | None = None
    # Detalle interno para el historial del pedido (sin secretos).
    detalle: str | None = None


def _resultado_de_error(
    error: ErrorVentasFF, *, codigo_previo: str | None = None
) -> ResultadoProveedor:
    if isinstance(error, ErrorAPI):
        if error.code in ERRORES_DE_CUENTA:
            # Errores de cuenta: alerta crítica y mensaje genérico al cliente (plan 4.2).
            return ResultadoProveedor(
                Clasificacion.ERROR_API,
                motivo=MENSAJE_SERVICIO_NO_DISPONIBLE,
                error_code=error.code,
                alerta=ALERTA_CUENTA,
                detalle=f"{error.code}: {error.mensaje}",
            )
        if error.code == "INSUFFICIENT_CREDIT":
            return ResultadoProveedor(
                Clasificacion.ERROR_API,
                motivo=MENSAJE_SIN_DISPONIBILIDAD,
                error_code=error.code,
                alerta=ALERTA_CREDITO,
                detalle=f"{error.code}: {error.mensaje}",
            )
        if error.code in ("BUSY", "RATE_LIMITED"):
            motivo = MENSAJE_PROVEEDOR_OCUPADO
        elif error.code == "PURCHASE_FAILED" and error.mensaje:
            # El texto del proveedor dice el motivo (ej. "Paquete no disponible").
            motivo = error.mensaje
        else:
            motivo = MENSAJE_ERROR_RECARGA
        return ResultadoProveedor(
            Clasificacion.ERROR_API,
            motivo=motivo,
            error_code=error.code,
            detalle=f"{error.code}: {error.mensaje}",
        )
    if isinstance(error, ErrorPrevioAlEnvio):
        return ResultadoProveedor(
            Clasificacion.ERROR_PREVIO,
            motivo=MENSAJE_SIN_CONEXION,
            error_code=codigo_previo or "SIN_CONEXION",
            detalle=str(error),
        )
    # ResultadoIncierto u otro: no se sabe si se cobró (RN-04).
    return ResultadoProveedor(Clasificacion.INCIERTO, detalle=str(error))


async def _verificar_credito(cliente: ClienteVentasFF, precio_costo) -> ResultadoProveedor | None:
    """RF-23: None si el crédito cubre el costo; si no, el resultado FALLIDO.

    Si `saldo.php` falla no se llegó a pedir la recarga, así que es seguro fallar.
    """
    try:
        saldo = await cliente.saldo()
    except ErrorAPI as error:
        return _resultado_de_error(error)
    except (ErrorPrevioAlEnvio, ResultadoIncierto) as error:
        return ResultadoProveedor(
            Clasificacion.ERROR_PREVIO,
            motivo=MENSAJE_SIN_CONEXION,
            error_code="SALDO_NO_VERIFICADO",
            detalle=f"saldo.php: {error}",
        )
    if saldo.credito < precio_costo:
        logger.warning("Crédito del proveedor insuficiente para la recarga")
        return ResultadoProveedor(
            Clasificacion.ERROR_PREVIO,
            motivo=MENSAJE_SIN_DISPONIBILIDAD,
            error_code="SIN_CREDITO_PROVEEDOR",
            alerta=ALERTA_CREDITO,
            detalle="Crédito del proveedor menor que el costo",
        )
    return None


async def llamar_proveedor(
    motor: AsyncEngine,
    cliente: ClienteVentasFF,
    limitador: LimitadorTasa,
    *,
    paquete_id: int,
    player_id: str,
    precio_costo,
    dormir: Callable[[float], Awaitable[None]] = asyncio.sleep,
) -> ResultadoProveedor:
    """Fase B (plan 4.2), fuera de la transacción de saldo.

    Candado global en una conexión dedicada (RN-05), limitador propio (RN-07),
    verificación de crédito (RF-23) y `recargar.php` con un reintento ante BUSY
    (RN-06). Nunca lanza `ErrorVentasFF`: devuelve el resultado clasificado.
    """
    async with motor.connect() as conexion:
        await conexion.execute(text("SELECT pg_advisory_lock(:clave)"), {"clave": CANDADO_RECARGAS})
        await conexion.commit()
        try:
            await limitador.adquirir()
            fallo_credito = await _verificar_credito(cliente, precio_costo)
            if fallo_credito is not None:
                return fallo_credito
            for intento in (1, 2):
                try:
                    recarga = await cliente.recargar(paquete_id, player_id)
                except ErrorAPI as error:
                    if error.code == "BUSY" and intento == 1:
                        logger.info("VentasFF BUSY: reintento en %.0fs", SEGUNDOS_REINTENTO_BUSY)
                        await dormir(SEGUNDOS_REINTENTO_BUSY)
                        continue
                    return _resultado_de_error(error)
                except ErrorVentasFF as error:
                    return _resultado_de_error(error)
                return ResultadoProveedor(Clasificacion.EXITO, recarga=recarga)
            raise AssertionError("inalcanzable")  # pragma: no cover
        finally:
            await conexion.execute(
                text("SELECT pg_advisory_unlock(:clave)"), {"clave": CANDADO_RECARGAS}
            )
            await conexion.commit()


# --- Fase C: resolución (plan 4.2) ---


async def bloquear_pedido(sesion: AsyncSession, pedido_id: int) -> Pedido:
    pedido = await sesion.scalar(
        select(Pedido)
        .where(Pedido.id == pedido_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if pedido is None:
        raise LookupError(f"No existe el pedido {pedido_id}")
    return pedido


async def aplicar_exito(
    sesion: AsyncSession,
    pedido: Pedido,
    referencia: str | None,
    *,
    detalle: str | None = None,
    creado_por: int | None = None,
) -> None:
    """EXITOSO: confirma el cobro de la reserva y guarda la referencia (RF-24)."""
    await cambiar_estado(sesion, pedido, Estado.EXITOSO, detalle=detalle, creado_por=creado_por)
    pedido.referencia = referencia
    await ledger.cargar(sesion, pedido.usuario_id, pedido.precio_venta, pedido_id=pedido.id)


async def aplicar_fallo(
    sesion: AsyncSession,
    pedido: Pedido,
    motivo: str,
    error_code: str | None,
    *,
    detalle: str | None = None,
    creado_por: int | None = None,
) -> None:
    """FALLIDO: libera la reserva y guarda el motivo (RF-24)."""
    await cambiar_estado(sesion, pedido, Estado.FALLIDO, detalle=detalle, creado_por=creado_por)
    pedido.error = motivo
    pedido.error_code = error_code
    await ledger.liberar(sesion, pedido.usuario_id, pedido.precio_venta, pedido_id=pedido.id)


async def resolver_pedido(
    sesion: AsyncSession, pedido_id: int, resultado: ResultadoProveedor
) -> Pedido:
    """Fase C: actualiza pedido y saldo según el resultado, en una transacción.

    Solo resuelve pedidos en PROCESANDO; si no, `TransicionInvalida` sin cambios.
    """
    try:
        pedido = await bloquear_pedido(sesion, pedido_id)
        match resultado.clasificacion:
            case Clasificacion.EXITO:
                referencia = resultado.recarga.referencia if resultado.recarga else None
                await aplicar_exito(sesion, pedido, referencia, detalle=f"Referencia {referencia}")
            case Clasificacion.ERROR_API | Clasificacion.ERROR_PREVIO:
                await aplicar_fallo(
                    sesion,
                    pedido,
                    resultado.motivo or MENSAJE_ERROR_RECARGA,
                    resultado.error_code,
                    detalle=resultado.detalle,
                )
            case _:
                # Timeout o respuesta ilegible: el monto queda retenido (RN-04).
                await cambiar_estado(
                    sesion, pedido, Estado.PENDIENTE_VERIFICAR, detalle=resultado.detalle
                )
        await sesion.commit()
    except Exception:
        await sesion.rollback()
        raise
    logger.info("Pedido %s resuelto: %s", pedido.codigo, pedido.estado)
    return pedido


async def procesar_pedido(
    fabrica: async_sessionmaker,
    motor: AsyncEngine,
    cliente: ClienteVentasFF,
    limitador: LimitadorTasa,
    pedido_id: int,
    *,
    dormir: Callable[[float], Awaitable[None]] = asyncio.sleep,
) -> tuple[Pedido, ResultadoProveedor]:
    """Fases B y C de un pedido ya creado en PROCESANDO."""
    async with fabrica() as sesion:
        pedido = await sesion.get(Pedido, pedido_id)
        if pedido is None:
            raise LookupError(f"No existe el pedido {pedido_id}")
        datos = (pedido.paquete_id, pedido.player_id, pedido.precio_costo, pedido.estado)
    paquete_id, player_id, precio_costo, estado = datos
    validar_transicion(estado, Estado.EXITOSO)  # solo pedidos en PROCESANDO

    resultado = await llamar_proveedor(
        motor,
        cliente,
        limitador,
        paquete_id=paquete_id,
        player_id=player_id,
        precio_costo=precio_costo,
        dormir=dormir,
    )
    if resultado.alerta:
        logger.warning("Alerta para el admin (%s): %s", resultado.alerta, resultado.error_code)
    async with fabrica() as sesion:
        pedido = await resolver_pedido(sesion, pedido_id, resultado)
    return pedido, resultado
