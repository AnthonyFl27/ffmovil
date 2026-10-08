"""T-040: tablas `pedidos` y `pedido_eventos` (RF-25, RF-27, RF-30)."""

from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.models import Movimiento, PedidoEvento
from app.models.pedidos import ESTADOS_PEDIDO
from app.services.estados import Estado
from tests.utilidades import crear_paquete, crear_pedido, crear_usuario


@pytest.fixture
async def datos(sesion_bd):
    usuario = await crear_usuario(sesion_bd)
    paquete = await crear_paquete(sesion_bd)
    return usuario.id, paquete


def test_estados_del_modelo_coinciden_con_la_maquina():
    assert ESTADOS_PEDIDO == tuple(Estado)


async def test_pedido_y_evento(sesion_bd, datos):
    usuario_id, paquete = datos
    pedido = await crear_pedido(sesion_bd, usuario_id, paquete, nickname=None)
    sesion_bd.add(PedidoEvento(pedido_id=pedido.id, estado_anterior=None, estado_nuevo="CREADO"))
    await sesion_bd.flush()
    await sesion_bd.refresh(pedido)
    assert pedido.precio_venta == Decimal("0.91")
    assert pedido.creado_en.tzinfo is not None
    assert pedido.codigo is None
    eventos = await sesion_bd.scalars(
        select(PedidoEvento.estado_nuevo).where(PedidoEvento.pedido_id == pedido.id)
    )
    assert list(eventos) == ["CREADO"]
    await sesion_bd.rollback()


async def test_mismo_token_otro_usuario_permitido(sesion_bd, datos):
    usuario_id, paquete = datos
    otro = await crear_usuario(sesion_bd)
    await crear_pedido(sesion_bd, usuario_id, paquete, token_idempotencia="tok-1")
    await crear_pedido(sesion_bd, otro.id, paquete, token_idempotencia="tok-1")
    await sesion_bd.rollback()


@pytest.mark.parametrize(
    ("cambios", "restriccion"),
    [
        ({"estado": "PERDIDO"}, "ck_pedidos_estado"),
        ({"player_id": "123"}, "ck_pedidos_player_id_formato"),
        ({"player_id": "1" * 21}, "ck_pedidos_player_id_formato"),
        ({"player_id": "7580744a"}, "ck_pedidos_player_id_formato"),
        ({"player_id": " 75807448"}, "ck_pedidos_player_id_formato"),
        ({"precio_venta": Decimal("0.00")}, "ck_pedidos_precio_venta_positivo"),
        ({"token_idempotencia": ""}, "ck_pedidos_token_no_vacio"),
        ({"paquete_id": -5}, "fk_pedidos_paquete_id_paquetes"),
    ],
)
async def test_pedido_invalido(sesion_bd, datos, cambios, restriccion):
    usuario_id, paquete = datos
    with pytest.raises(IntegrityError, match=restriccion):
        await crear_pedido(sesion_bd, usuario_id, paquete, **cambios)
    await sesion_bd.rollback()


@pytest.mark.parametrize("player_id", ["1234", "1" * 20])
async def test_player_id_en_limites(sesion_bd, datos, player_id):
    usuario_id, paquete = datos
    await crear_pedido(sesion_bd, usuario_id, paquete, player_id=player_id)
    await sesion_bd.rollback()


@pytest.mark.parametrize(
    ("campo", "restriccion"),
    [("token_idempotencia", "uq_pedidos_usuario_token"), ("codigo", "uq_pedidos_codigo")],
)
async def test_unicidad(sesion_bd, datos, campo, restriccion):
    usuario_id, paquete = datos
    await crear_pedido(sesion_bd, usuario_id, paquete, **{campo: "repetido"})
    with pytest.raises(IntegrityError, match=restriccion):
        await crear_pedido(sesion_bd, usuario_id, paquete, **{campo: "repetido"})
    await sesion_bd.rollback()


async def test_movimiento_con_pedido_inexistente_falla(sesion_bd, datos):
    usuario_id, _ = datos
    sesion_bd.add(
        Movimiento(
            usuario_id=usuario_id,
            tipo="reserva",
            monto=Decimal("1.00"),
            saldo_disponible_resultante=Decimal(0),
            saldo_reservado_resultante=Decimal("1.00"),
            pedido_id=-1,
        )
    )
    with pytest.raises(IntegrityError, match="fk_movimientos_pedido_id_pedidos"):
        await sesion_bd.flush()
    await sesion_bd.rollback()
