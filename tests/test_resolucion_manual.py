"""T-048: resolución manual de PENDIENTE_VERIFICAR por el admin (RF-52, RN-04, RF-55)."""

from decimal import Decimal

import pytest
from sqlalchemy import select

from app.models import Auditoria, Movimiento, Pedido, PedidoEvento, Saldo
from app.services import ledger
from app.services.estados import TransicionInvalida
from app.services.recarga_service import (
    CODIGO_FALLIDO_POR_ADMIN,
    MENSAJE_FALLIDO_POR_ADMIN,
    ErrorResolucion,
    resolver_pendiente,
)
from tests.utilidades import crear_paquete, crear_pedido

D = Decimal


async def pedido_con_reserva(sesion, usuario_id, admin_id, estado="PENDIENTE_VERIFICAR"):
    """Cliente con 10.00, un pedido de 0.91 reservado en el estado indicado."""
    await ledger.abonar(sesion, usuario_id, D("10.00"), nota="abono", creado_por=admin_id)
    paquete = await crear_paquete(sesion)
    pedido = await crear_pedido(sesion, usuario_id, paquete, estado=estado)
    pedido.codigo = f"FF-T{pedido.id}"
    await ledger.reservar(sesion, usuario_id, pedido.precio_venta, pedido_id=pedido.id)
    await sesion.commit()
    return pedido.id


async def estado_de(sesion, usuario_id, pedido_id):
    pedido = await sesion.scalar(
        select(Pedido).where(Pedido.id == pedido_id).execution_options(populate_existing=True)
    )
    saldo = await sesion.scalar(
        select(Saldo)
        .where(Saldo.usuario_id == usuario_id)
        .execution_options(populate_existing=True)
    )
    tipos = list(
        await sesion.scalars(
            select(Movimiento.tipo).where(Movimiento.pedido_id == pedido_id).order_by(Movimiento.id)
        )
    )
    return pedido, (saldo.saldo_disponible, saldo.saldo_reservado), tipos


async def test_marcar_exitoso(sesion_bd, cuenta, admin_id):
    pedido_id = await pedido_con_reserva(sesion_bd, cuenta, admin_id)
    await resolver_pendiente(
        sesion_bd,
        pedido_id,
        "exitoso",
        admin_id=admin_id,
        nota="Verificado en el panel de VentasFF",
        referencia=" EV-ABCDEF12 ",
        ip="192.0.2.10",
    )
    pedido, saldo, tipos = await estado_de(sesion_bd, cuenta, pedido_id)
    assert (pedido.estado, pedido.referencia, pedido.error) == ("EXITOSO", "EV-ABCDEF12", None)
    assert saldo == (D("9.09"), D("0.00"))
    assert tipos == ["reserva", "cargo"]

    evento = await sesion_bd.scalar(select(PedidoEvento).where(PedidoEvento.pedido_id == pedido_id))
    assert (evento.estado_anterior, evento.estado_nuevo, evento.creado_por) == (
        "PENDIENTE_VERIFICAR",
        "EXITOSO",
        admin_id,
    )
    assert evento.detalle == "Verificado en el panel de VentasFF"
    auditoria = await sesion_bd.scalar(
        select(Auditoria).where(
            Auditoria.accion == "resolver_pedido",
            Auditoria.detalle["pedido"].astext == pedido.codigo,
        )
    )
    assert auditoria.usuario_id == admin_id
    assert auditoria.detalle["resultado"] == "exitoso"
    assert str(auditoria.ip) == "192.0.2.10"


async def test_marcar_fallido(sesion_bd, cuenta, admin_id):
    pedido_id = await pedido_con_reserva(sesion_bd, cuenta, admin_id)
    await resolver_pendiente(
        sesion_bd, pedido_id, "fallido", admin_id=admin_id, nota="No figura en VentasFF"
    )
    pedido, saldo, tipos = await estado_de(sesion_bd, cuenta, pedido_id)
    assert (pedido.estado, pedido.error, pedido.error_code) == (
        "FALLIDO",
        MENSAJE_FALLIDO_POR_ADMIN,
        CODIGO_FALLIDO_POR_ADMIN,
    )
    assert saldo == (D("10.00"), D("0.00"))
    assert tipos == ["reserva", "liberacion"]


@pytest.mark.parametrize("estado", ["PROCESANDO", "EXITOSO", "FALLIDO"])
async def test_rechaza_estados_que_no_son_pendiente(sesion_bd, cuenta, admin_id, estado):
    pedido_id = await pedido_con_reserva(sesion_bd, cuenta, admin_id, estado=estado)
    with pytest.raises(TransicionInvalida):
        await resolver_pendiente(sesion_bd, pedido_id, "exitoso", admin_id=admin_id, nota="x")
    pedido, saldo, tipos = await estado_de(sesion_bd, cuenta, pedido_id)
    assert pedido.estado == estado
    assert (saldo, tipos) == ((D("9.09"), D("0.91")), ["reserva"])


async def test_solo_un_admin_puede_resolver(sesion_bd, cuenta, admin_id):
    pedido_id = await pedido_con_reserva(sesion_bd, cuenta, admin_id)
    with pytest.raises(ErrorResolucion):
        await resolver_pendiente(sesion_bd, pedido_id, "exitoso", admin_id=cuenta, nota="x")
    pedido, _, _ = await estado_de(sesion_bd, cuenta, pedido_id)
    assert pedido.estado == "PENDIENTE_VERIFICAR"


@pytest.mark.parametrize(
    ("resultado", "nota"), [("exitoso", "  "), ("exitoso", None), ("talvez", "x")]
)
async def test_datos_invalidos(sesion_bd, admin_id, resultado, nota):
    with pytest.raises(ErrorResolucion):
        await resolver_pendiente(sesion_bd, -1, resultado, admin_id=admin_id, nota=nota)
