"""T-014: dos reservas simultáneas con saldo para una sola (CA-01, RNF-02)."""

import asyncio
import time
from decimal import Decimal

from sqlalchemy import func, select

from app.db import crear_fabrica_sesiones
from app.models import Movimiento, Saldo
from app.services import ledger
from app.services.ledger import SaldoInsuficiente

PRECIO = Decimal("6.00")
RETENCION = 1.5  # segundos que la primera transacción mantiene el candado


async def con_fondos(sesion, usuario_id, admin_id):
    await ledger.abonar(sesion, usuario_id, Decimal("10.00"), nota="abono", creado_por=admin_id)
    await sesion.commit()


async def reservar(fabrica, usuario_id, antes_de_confirmar=None) -> str:
    async with fabrica() as sesion:
        try:
            await ledger.reservar(sesion, usuario_id, PRECIO)
        except SaldoInsuficiente:
            await sesion.rollback()
            return "rechazada"
        if antes_de_confirmar is not None:
            await antes_de_confirmar()
        await sesion.commit()
        return "reservada"


async def verificar_una_sola_reserva(sesion, usuario_id):
    saldo = await sesion.scalar(
        select(Saldo)
        .where(Saldo.usuario_id == usuario_id)
        .execution_options(populate_existing=True)
    )
    assert (saldo.saldo_disponible, saldo.saldo_reservado) == (Decimal("4.00"), PRECIO)
    reservas = await sesion.scalar(
        select(func.count())
        .select_from(Movimiento)
        .where(Movimiento.usuario_id == usuario_id, Movimiento.tipo == "reserva")
    )
    assert reservas == 1


async def test_la_segunda_reserva_espera_y_se_rechaza(sesion_bd, motor_bd, cuenta, admin_id):
    await con_fondos(sesion_bd, cuenta, admin_id)
    fabrica = crear_fabrica_sesiones(motor_bd)
    primera_bloqueo = asyncio.Event()

    async def retener():
        primera_bloqueo.set()
        await asyncio.sleep(RETENCION)

    async def segunda():
        await primera_bloqueo.wait()
        inicio = time.monotonic()
        resultado = await reservar(fabrica, cuenta)
        return resultado, time.monotonic() - inicio

    primera, (resultado_segunda, espera) = await asyncio.gather(
        reservar(fabrica, cuenta, antes_de_confirmar=retener), segunda()
    )

    assert (primera, resultado_segunda) == ("reservada", "rechazada")
    # La segunda quedó bloqueada en FOR UPDATE hasta el commit de la primera.
    assert espera >= RETENCION * 0.8
    await verificar_una_sola_reserva(sesion_bd, cuenta)


async def test_carrera_simultanea(sesion_bd, motor_bd, cuenta, admin_id):
    await con_fondos(sesion_bd, cuenta, admin_id)
    fabrica = crear_fabrica_sesiones(motor_bd)

    resultados = await asyncio.gather(reservar(fabrica, cuenta), reservar(fabrica, cuenta))

    assert sorted(resultados) == ["rechazada", "reservada"]
    await verificar_una_sola_reserva(sesion_bd, cuenta)
