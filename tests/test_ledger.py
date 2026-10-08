"""T-012: operaciones del servicio `ledger` (RF-22, RF-24, RF-40 a RF-42, RN-01, RNF-02)."""

from decimal import Decimal

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError

from app.models import Movimiento, Saldo
from app.services import ledger
from app.services.ledger import (
    CuentaInexistente,
    MontoInvalido,
    NotaObligatoria,
    ReservaInsuficiente,
    SaldoInsuficiente,
)

D = Decimal


async def saldo_de(sesion, usuario_id) -> tuple[Decimal, Decimal]:
    saldo = await sesion.scalar(
        select(Saldo)
        .where(Saldo.usuario_id == usuario_id)
        .execution_options(populate_existing=True)
    )
    return saldo.saldo_disponible, saldo.saldo_reservado


async def movimientos_de(sesion, usuario_id) -> list[Movimiento]:
    return list(
        await sesion.scalars(
            select(Movimiento).where(Movimiento.usuario_id == usuario_id).order_by(Movimiento.id)
        )
    )


@pytest.fixture
async def con_fondos(sesion_bd, cuenta, admin_id):
    """Cliente con 10.00 disponibles."""
    await ledger.abonar(sesion_bd, cuenta, D("10.00"), nota="transferencia", creado_por=admin_id)
    await sesion_bd.commit()
    return cuenta


async def test_abrir_cuenta_en_cero(sesion_bd, cuenta):
    assert await saldo_de(sesion_bd, cuenta) == (D("0.00"), D("0.00"))
    assert await movimientos_de(sesion_bd, cuenta) == []


async def test_abonar(sesion_bd, cuenta, admin_id):
    mov = await ledger.abonar(
        sesion_bd, cuenta, D("25.50"), nota="  Yape op. 123  ", creado_por=admin_id
    )
    await sesion_bd.commit()
    assert await saldo_de(sesion_bd, cuenta) == (D("25.50"), D("0.00"))
    assert (mov.tipo, mov.monto, mov.nota, mov.creado_por) == (
        "abono",
        D("25.50"),
        "Yape op. 123",
        admin_id,
    )
    assert (mov.saldo_disponible_resultante, mov.saldo_reservado_resultante) == (
        D("25.50"),
        D("0.00"),
    )


@pytest.mark.parametrize("monto", [D("2.50"), D("-4.00"), D("-10.00")])
async def test_ajustar(sesion_bd, con_fondos, admin_id, monto):
    mov = await ledger.ajustar(sesion_bd, con_fondos, monto, nota="corrección", creado_por=admin_id)
    await sesion_bd.commit()
    assert mov.tipo == "ajuste"
    assert mov.monto == monto
    assert await saldo_de(sesion_bd, con_fondos) == (D("10.00") + monto, D("0.00"))


async def test_ajuste_no_deja_saldo_negativo(sesion_bd, con_fondos, admin_id):
    with pytest.raises(SaldoInsuficiente):
        await ledger.ajustar(
            sesion_bd, con_fondos, D("-10.01"), nota="corrección", creado_por=admin_id
        )
    await sesion_bd.rollback()
    assert await saldo_de(sesion_bd, con_fondos) == (D("10.00"), D("0.00"))


async def test_reservar(sesion_bd, con_fondos):
    mov = await ledger.reservar(sesion_bd, con_fondos, D("0.91"))
    await sesion_bd.commit()
    assert mov.tipo == "reserva"
    assert await saldo_de(sesion_bd, con_fondos) == (D("9.09"), D("0.91"))
    assert (mov.saldo_disponible_resultante, mov.saldo_reservado_resultante) == (
        D("9.09"),
        D("0.91"),
    )


async def test_reservar_todo_el_saldo(sesion_bd, con_fondos):
    await ledger.reservar(sesion_bd, con_fondos, D("10.00"))
    await sesion_bd.commit()
    assert await saldo_de(sesion_bd, con_fondos) == (D("0.00"), D("10.00"))


async def test_reservar_sin_saldo(sesion_bd, con_fondos):
    with pytest.raises(SaldoInsuficiente):
        await ledger.reservar(sesion_bd, con_fondos, D("10.01"))
    await sesion_bd.rollback()
    assert await saldo_de(sesion_bd, con_fondos) == (D("10.00"), D("0.00"))
    assert len(await movimientos_de(sesion_bd, con_fondos)) == 1


async def test_liberar(sesion_bd, con_fondos):
    await ledger.reservar(sesion_bd, con_fondos, D("3.00"))
    mov = await ledger.liberar(sesion_bd, con_fondos, D("3.00"))
    await sesion_bd.commit()
    assert mov.tipo == "liberacion"
    assert await saldo_de(sesion_bd, con_fondos) == (D("10.00"), D("0.00"))


async def test_cargar(sesion_bd, con_fondos):
    await ledger.reservar(sesion_bd, con_fondos, D("3.00"))
    mov = await ledger.cargar(sesion_bd, con_fondos, D("3.00"))
    await sesion_bd.commit()
    assert mov.tipo == "cargo"
    assert await saldo_de(sesion_bd, con_fondos) == (D("7.00"), D("0.00"))
    tipos = [m.tipo for m in await movimientos_de(sesion_bd, con_fondos)]
    assert tipos == ["abono", "reserva", "cargo"]


@pytest.mark.parametrize("operacion", [ledger.liberar, ledger.cargar])
async def test_no_libera_ni_cobra_mas_de_lo_reservado(sesion_bd, con_fondos, operacion):
    await ledger.reservar(sesion_bd, con_fondos, D("1.00"))
    with pytest.raises(ReservaInsuficiente):
        await operacion(sesion_bd, con_fondos, D("1.01"))
    await sesion_bd.rollback()


@pytest.mark.parametrize(
    "monto",
    [0.81, 1, D("0"), D("-1.00"), D("0.001"), D("NaN"), D("Infinity"), D("10000000000.00")],
    ids=["float", "int", "cero", "negativo", "3_decimales", "nan", "infinito", "excede"],
)
async def test_monto_invalido(sesion_bd, cuenta, admin_id, monto):
    with pytest.raises(MontoInvalido):
        await ledger.abonar(sesion_bd, cuenta, monto, nota="x", creado_por=admin_id)
    with pytest.raises(MontoInvalido):
        await ledger.reservar(sesion_bd, cuenta, monto)
    await sesion_bd.rollback()


async def test_ajuste_cero_invalido(sesion_bd, cuenta, admin_id):
    with pytest.raises(MontoInvalido):
        await ledger.ajustar(sesion_bd, cuenta, D("0.00"), nota="x", creado_por=admin_id)


@pytest.mark.parametrize("operacion", [ledger.abonar, ledger.ajustar])
@pytest.mark.parametrize("nota", [None, "", "   "])
async def test_nota_obligatoria(sesion_bd, cuenta, admin_id, operacion, nota):
    with pytest.raises(NotaObligatoria):
        await operacion(sesion_bd, cuenta, D("1.00"), nota=nota, creado_por=admin_id)


async def test_cuenta_inexistente(sesion_bd):
    with pytest.raises(CuentaInexistente):
        await ledger.reservar(sesion_bd, -1, D("1.00"))
    await sesion_bd.rollback()


async def test_guarda_pedido_id(sesion_bd, con_fondos):
    mov = await ledger.reservar(sesion_bd, con_fondos, D("1.00"), pedido_id=123)
    await sesion_bd.commit()
    assert mov.pedido_id == 123


async def test_bloquea_la_fila_de_saldo(sesion_bd, motor_bd, con_fondos):
    """La operación deja la fila bloqueada hasta el fin de la transacción (FOR UPDATE)."""
    await ledger.reservar(sesion_bd, con_fondos, D("1.00"))
    async with motor_bd.connect() as otra:
        with pytest.raises(DBAPIError, match="could not obtain lock"):
            await otra.execute(
                text("SELECT 1 FROM saldos WHERE usuario_id = :id FOR UPDATE NOWAIT"),
                {"id": con_fondos},
            )
    await sesion_bd.rollback()
