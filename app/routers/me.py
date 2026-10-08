"""Datos del propio cliente: resumen, fondos e historial (RF-31 a RF-36)."""

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import func, select

from app.models import Movimiento, Paquete, Pedido, Saldo
from app.routers.dependencias import Bd, Cliente
from app.schemas.cliente import (
    Fondos,
    ListaPedidosCliente,
    MovimientoFondos,
    PedidoCliente,
    Resumen,
)
from app.services.codigos import id_desde_codigo
from app.services.consultas_pedidos import (
    POR_PAGINA,
    POR_PAGINA_MAXIMO,
    FiltrosPedido,
    paginar,
)
from app.services.estados import ETIQUETAS_CLIENTE, Estado

router = APIRouter(prefix="/me", tags=["cliente"])


@router.get("/resumen", response_model=Resumen)
async def resumen(actual: Cliente, bd: Bd):
    de_exitosos = (Pedido.usuario_id == actual.usuario_id, Pedido.estado == Estado.EXITOSO)
    gasto = select(func.coalesce(func.sum(Pedido.precio_venta), 0)).where(*de_exitosos)
    recargas = select(func.count()).select_from(Pedido).where(*de_exitosos)
    fila = (
        await bd.execute(
            select(
                Saldo.saldo_disponible,
                Saldo.saldo_reservado,
                gasto.scalar_subquery().label("gasto"),
                recargas.scalar_subquery().label("recargas"),
            ).where(Saldo.usuario_id == actual.usuario_id)
        )
    ).one()
    return Resumen(
        saldo_disponible=fila.saldo_disponible,
        saldo_reservado=fila.saldo_reservado,
        gasto_total=fila.gasto,
        recargas=fila.recargas,
    )


@router.get("/fondos", response_model=Fondos)
async def fondos(actual: Cliente, bd: Bd):
    saldo = await bd.get(Saldo, actual.usuario_id)
    movimientos = await bd.scalars(
        select(Movimiento)
        .where(
            Movimiento.usuario_id == actual.usuario_id,
            Movimiento.tipo.in_(("abono", "ajuste")),
        )
        .order_by(Movimiento.fecha.desc(), Movimiento.id.desc())
    )
    return Fondos(
        saldo_disponible=saldo.saldo_disponible,
        saldo_reservado=saldo.saldo_reservado,
        movimientos=[MovimientoFondos.model_validate(m) for m in movimientos],
    )


MENSAJE_PEDIDO_NO_ENCONTRADO = "Pedido no encontrado."


def consulta_pedidos_cliente(usuario_id: int):
    return (
        select(Pedido, Paquete.nombre, Paquete.diamantes)
        .join(Paquete, Paquete.paquete_id == Pedido.paquete_id)
        .where(Pedido.usuario_id == usuario_id)
    )


def pedido_cliente(pedido: Pedido, nombre: str, diamantes: int | None) -> PedidoCliente:
    return PedidoCliente(
        codigo=pedido.codigo,
        fecha=pedido.creado_en,
        paquete=nombre,
        diamantes=diamantes,
        player_id=pedido.player_id,
        nickname=pedido.nickname,
        monto=pedido.precio_venta,
        estado=pedido.estado,
        estado_etiqueta=ETIQUETAS_CLIENTE[Estado(pedido.estado)],
        referencia=pedido.referencia,
        motivo=pedido.error if pedido.estado == Estado.FALLIDO else None,
    )


@router.get("/pedidos", response_model=ListaPedidosCliente)
async def pedidos(
    actual: Cliente,
    bd: Bd,
    estado: Estado | None = None,
    desde: datetime | None = None,
    hasta: datetime | None = None,
    player_id: str | None = None,
    codigo: str | None = None,
    pagina: Annotated[int, Query(ge=1)] = 1,
    por_pagina: Annotated[int, Query(ge=1, le=POR_PAGINA_MAXIMO)] = POR_PAGINA,
):
    """Historial propio con filtros (RF-31, RF-32), incluidos los fallidos (CA-05)."""
    filtros = FiltrosPedido(estado, desde, hasta, player_id, codigo)
    resultado = await paginar(
        bd, filtros.aplicar(consulta_pedidos_cliente(actual.usuario_id)), pagina, por_pagina
    )
    return ListaPedidosCliente(
        pedidos=[pedido_cliente(*fila) for fila in resultado.filas],
        total=resultado.total,
        pagina=resultado.pagina,
        por_pagina=resultado.por_pagina,
    )


@router.get("/pedidos/{codigo}", response_model=PedidoCliente)
async def pedido(codigo: str, actual: Cliente, bd: Bd):
    """Detalle de un pedido propio; uno ajeno o inexistente da 404 (RF-31)."""
    pedido_id = id_desde_codigo(codigo)
    fila = None
    if pedido_id is not None:
        fila = (
            await bd.execute(
                consulta_pedidos_cliente(actual.usuario_id).where(Pedido.id == pedido_id)
            )
        ).first()
    if fila is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, MENSAJE_PEDIDO_NO_ENCONTRADO)
    return pedido_cliente(*fila)
