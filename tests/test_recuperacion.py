"""T-047: recuperación de pedidos huérfanos tras reinicio (RN-09, RN-04)."""

from datetime import timedelta

from sqlalchemy import select

from app.models import Movimiento, Pedido, PedidoEvento
from app.services.recuperacion import DETALLE_RECUPERACION, recuperar_pedidos_huerfanos
from tests.utilidades import crear_paquete, crear_pedido


async def _pedido_con_codigo(sesion, cuenta, paquete, estado):
    pedido = await crear_pedido(sesion, cuenta, paquete, estado=estado)
    pedido.codigo = f"FF-T{pedido.id}"
    await sesion.commit()
    return pedido


async def _releer(sesion, pedido_id):
    return await sesion.scalar(
        select(Pedido).where(Pedido.id == pedido_id).execution_options(populate_existing=True)
    )


async def test_recupera_solo_procesando_sin_movimientos(sesion_bd, cuenta):
    paquete = await crear_paquete(sesion_bd)
    huerfano_1 = await _pedido_con_codigo(sesion_bd, cuenta, paquete, "PROCESANDO")
    huerfano_2 = await _pedido_con_codigo(sesion_bd, cuenta, paquete, "PROCESANDO")
    exitoso = await _pedido_con_codigo(sesion_bd, cuenta, paquete, "EXITOSO")
    pendiente = await _pedido_con_codigo(sesion_bd, cuenta, paquete, "PENDIENTE_VERIFICAR")

    codigos = await recuperar_pedidos_huerfanos(sesion_bd)

    assert huerfano_1.codigo in codigos
    assert huerfano_2.codigo in codigos
    for huerfano in (huerfano_1, huerfano_2):
        recuperado = await _releer(sesion_bd, huerfano.id)
        assert recuperado.estado == "PENDIENTE_VERIFICAR"
        eventos = (
            await sesion_bd.scalars(
                select(PedidoEvento).where(PedidoEvento.pedido_id == huerfano.id)
            )
        ).all()
        assert [(e.estado_anterior, e.estado_nuevo, e.detalle) for e in eventos] == [
            ("PROCESANDO", "PENDIENTE_VERIFICAR", DETALLE_RECUPERACION)
        ]
    assert (await _releer(sesion_bd, exitoso.id)).estado == "EXITOSO"
    assert (await _releer(sesion_bd, pendiente.id)).estado == "PENDIENTE_VERIFICAR"

    movimientos = await sesion_bd.scalars(
        select(Movimiento).where(Movimiento.pedido_id.in_([huerfano_1.id, huerfano_2.id]))
    )
    assert movimientos.all() == []


async def test_umbral_de_antiguedad_no_recupera_pedido_reciente(sesion_bd, cuenta):
    paquete = await crear_paquete(sesion_bd)
    reciente = await _pedido_con_codigo(sesion_bd, cuenta, paquete, "PROCESANDO")

    codigos = await recuperar_pedidos_huerfanos(sesion_bd, antiguedad_minima=timedelta(hours=1))

    assert reciente.codigo not in codigos
    assert (await _releer(sesion_bd, reciente.id)).estado == "PROCESANDO"


async def test_segunda_llamada_no_devuelve_pedidos_ya_recuperados(sesion_bd, cuenta):
    paquete = await crear_paquete(sesion_bd)
    pedido = await _pedido_con_codigo(sesion_bd, cuenta, paquete, "PROCESANDO")

    primera = await recuperar_pedidos_huerfanos(sesion_bd)
    segunda = await recuperar_pedidos_huerfanos(sesion_bd)

    assert pedido.codigo in primera
    assert pedido.codigo not in segunda
