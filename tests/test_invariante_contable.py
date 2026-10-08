"""T-013: saldo = suma de movimientos tras una secuencia aleatoria (CA-04)."""

import random
from decimal import Decimal

import pytest
from sqlalchemy import case, func, select

from app.models import Movimiento, Saldo
from app.models.saldos import TIPOS_MOVIMIENTO
from app.services import ledger
from app.services.ledger import ErrorLedger

OPERACIONES = 30


def monto_aleatorio(azar: random.Random, maximo: int = 2000) -> Decimal:
    return Decimal(azar.randint(1, maximo)) / 100


def suma_por_tipo(*tipos: str):
    return func.coalesce(func.sum(case((Movimiento.tipo.in_(tipos), Movimiento.monto), else_=0)), 0)


@pytest.mark.parametrize("semilla", [7, 2026])
async def test_saldo_igual_a_suma_de_movimientos(sesion_bd, cuenta, admin_id, semilla):
    azar = random.Random(semilla)
    # Modelo esperado, independiente del ledger.
    disponible, reservado = Decimal(0), Decimal(0)
    rechazadas = 0

    for _ in range(OPERACIONES):
        operacion = azar.choice(["abono", "ajuste", "reserva", "liberacion", "cargo"])
        # A veces se piden montos mayores que el saldo, para cubrir los rechazos.
        monto = monto_aleatorio(azar)
        try:
            if operacion == "abono":
                await ledger.abonar(sesion_bd, cuenta, monto, nota="abono", creado_por=admin_id)
                disponible += monto
            elif operacion == "ajuste":
                monto = monto if azar.random() < 0.5 else -monto
                await ledger.ajustar(sesion_bd, cuenta, monto, nota="ajuste", creado_por=admin_id)
                disponible += monto
            elif operacion == "reserva":
                await ledger.reservar(sesion_bd, cuenta, monto)
                disponible, reservado = disponible - monto, reservado + monto
            elif operacion == "liberacion":
                await ledger.liberar(sesion_bd, cuenta, monto)
                disponible, reservado = disponible + monto, reservado - monto
            else:
                await ledger.cargar(sesion_bd, cuenta, monto)
                reservado -= monto
        except ErrorLedger:
            rechazadas += 1
    await sesion_bd.commit()
    assert 0 < rechazadas < OPERACIONES

    saldo = await sesion_bd.scalar(
        select(Saldo).where(Saldo.usuario_id == cuenta).execution_options(populate_existing=True)
    )
    assert (saldo.saldo_disponible, saldo.saldo_reservado) == (disponible, reservado)

    sumas = (
        await sesion_bd.execute(
            select(
                suma_por_tipo("abono", "ajuste", "liberacion") - suma_por_tipo("reserva"),
                suma_por_tipo("reserva") - suma_por_tipo("liberacion", "cargo"),
            ).where(Movimiento.usuario_id == cuenta)
        )
    ).one()
    assert tuple(sumas) == (saldo.saldo_disponible, saldo.saldo_reservado)

    # Cada movimiento parte de los saldos que dejó el anterior.
    movimientos = list(
        await sesion_bd.scalars(
            select(Movimiento).where(Movimiento.usuario_id == cuenta).order_by(Movimiento.id)
        )
    )
    assert {mov.tipo for mov in movimientos} == set(TIPOS_MOVIMIENTO)
    disp, res = Decimal(0), Decimal(0)
    for mov in movimientos:
        efecto = {
            "abono": (mov.monto, 0),
            "ajuste": (mov.monto, 0),
            "reserva": (-mov.monto, mov.monto),
            "liberacion": (mov.monto, -mov.monto),
            "cargo": (0, -mov.monto),
        }[mov.tipo]
        disp, res = disp + efecto[0], res + efecto[1]
        assert (mov.saldo_disponible_resultante, mov.saldo_reservado_resultante) == (disp, res)
