"""Libro contable: único punto que modifica saldos (RF-42, RNF-02).

Cada operación bloquea la fila de `saldos` con `SELECT … FOR UPDATE`, valida,
actualiza el saldo e inserta un movimiento con los saldos resultantes. No hace
commit: corre dentro de la transacción de quien la llama, para que la reserva
y la creación del pedido sean atómicas (plan, sec. 4.2).
"""

from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Movimiento, Saldo

CENTAVO = Decimal("0.01")
# Máximo de NUMERIC(12,2).
MONTO_MAXIMO = Decimal("9999999999.99")


class ErrorLedger(Exception):
    """Operación contable rechazada; no se modificó ningún saldo."""


class MontoInvalido(ErrorLedger):
    pass


class NotaObligatoria(ErrorLedger):
    pass


class CuentaInexistente(ErrorLedger):
    pass


class SaldoInsuficiente(ErrorLedger):
    """El saldo disponible no alcanza (RN-01)."""


class ReservaInsuficiente(ErrorLedger):
    """Se intentó liberar o cobrar más de lo reservado."""


def _validar_monto(monto: Decimal, *, con_signo: bool = False) -> Decimal:
    # bool es subclase de int, no de Decimal; float e int se rechazan (RNF-04).
    if not isinstance(monto, Decimal) or not monto.is_finite():
        raise MontoInvalido("El monto debe ser un Decimal finito")
    if monto != monto.quantize(CENTAVO):
        raise MontoInvalido("El monto admite como máximo 2 decimales")
    if abs(monto) > MONTO_MAXIMO:
        raise MontoInvalido("El monto excede el máximo permitido")
    if con_signo and monto == 0:
        raise MontoInvalido("El ajuste no puede ser 0")
    if not con_signo and monto <= 0:
        raise MontoInvalido("El monto debe ser mayor que 0")
    return monto.quantize(CENTAVO)


def _validar_nota(nota: str | None) -> str:
    if nota is None or not nota.strip():
        raise NotaObligatoria("La nota es obligatoria")
    return nota.strip()


async def abrir_cuenta(sesion: AsyncSession, usuario_id: int) -> Saldo:
    """Crea el saldo en cero de un usuario nuevo (no genera movimiento)."""
    saldo = Saldo(usuario_id=usuario_id, saldo_disponible=Decimal(0), saldo_reservado=Decimal(0))
    sesion.add(saldo)
    await sesion.flush()
    return saldo


async def _bloquear(sesion: AsyncSession, usuario_id: int) -> Saldo:
    saldo = await sesion.scalar(
        select(Saldo)
        .where(Saldo.usuario_id == usuario_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if saldo is None:
        raise CuentaInexistente(f"El usuario {usuario_id} no tiene cuenta de saldo")
    return saldo


async def _registrar(
    sesion: AsyncSession,
    saldo: Saldo,
    tipo: str,
    monto: Decimal,
    *,
    pedido_id: int | None = None,
    nota: str | None = None,
    creado_por: int | None = None,
) -> Movimiento:
    registro = Movimiento(
        usuario_id=saldo.usuario_id,
        tipo=tipo,
        monto=monto,
        saldo_disponible_resultante=saldo.saldo_disponible,
        saldo_reservado_resultante=saldo.saldo_reservado,
        pedido_id=pedido_id,
        nota=nota,
        creado_por=creado_por,
    )
    sesion.add(registro)
    await sesion.flush()
    return registro


async def abonar(
    sesion: AsyncSession, usuario_id: int, monto: Decimal, *, nota: str, creado_por: int
) -> Movimiento:
    """Abono manual del admin (RF-40)."""
    monto = _validar_monto(monto)
    nota = _validar_nota(nota)
    saldo = await _bloquear(sesion, usuario_id)
    saldo.saldo_disponible += monto
    return await _registrar(sesion, saldo, "abono", monto, nota=nota, creado_por=creado_por)


async def ajustar(
    sesion: AsyncSession, usuario_id: int, monto: Decimal, *, nota: str, creado_por: int
) -> Movimiento:
    """Ajuste positivo o negativo del disponible (RF-41)."""
    monto = _validar_monto(monto, con_signo=True)
    nota = _validar_nota(nota)
    saldo = await _bloquear(sesion, usuario_id)
    if saldo.saldo_disponible + monto < 0:
        raise SaldoInsuficiente("El ajuste dejaría el saldo disponible en negativo")
    saldo.saldo_disponible += monto
    return await _registrar(sesion, saldo, "ajuste", monto, nota=nota, creado_por=creado_por)


async def reservar(
    sesion: AsyncSession, usuario_id: int, monto: Decimal, *, pedido_id: int | None = None
) -> Movimiento:
    """Retiene el precio de una recarga antes de llamar al proveedor (RF-22)."""
    monto = _validar_monto(monto)
    saldo = await _bloquear(sesion, usuario_id)
    if saldo.saldo_disponible < monto:
        raise SaldoInsuficiente("Saldo disponible insuficiente")
    saldo.saldo_disponible -= monto
    saldo.saldo_reservado += monto
    return await _registrar(sesion, saldo, "reserva", monto, pedido_id=pedido_id)


async def liberar(
    sesion: AsyncSession, usuario_id: int, monto: Decimal, *, pedido_id: int | None = None
) -> Movimiento:
    """Devuelve al disponible una reserva de un pedido fallido (RF-24)."""
    monto = _validar_monto(monto)
    saldo = await _bloquear(sesion, usuario_id)
    if saldo.saldo_reservado < monto:
        raise ReservaInsuficiente("No hay saldo reservado suficiente para liberar")
    saldo.saldo_reservado -= monto
    saldo.saldo_disponible += monto
    return await _registrar(sesion, saldo, "liberacion", monto, pedido_id=pedido_id)


async def cargar(
    sesion: AsyncSession, usuario_id: int, monto: Decimal, *, pedido_id: int | None = None
) -> Movimiento:
    """Confirma el cobro de una reserva de un pedido exitoso (RF-24)."""
    monto = _validar_monto(monto)
    saldo = await _bloquear(sesion, usuario_id)
    if saldo.saldo_reservado < monto:
        raise ReservaInsuficiente("No hay saldo reservado suficiente para cobrar")
    saldo.saldo_reservado -= monto
    return await _registrar(sesion, saldo, "cargo", monto, pedido_id=pedido_id)
