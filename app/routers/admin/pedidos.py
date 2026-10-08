"""Pedidos para el admin: listado, detalle, ganancia y resolución manual (RF-50 a RF-52, RF-54)."""

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, Request, status
from sqlalchemy import func, select

from app.models import Paquete, Pedido, PedidoEvento, Usuario
from app.routers.dependencias import Admin, Bd, ip_cliente
from app.schemas.admin import (
    DetallePedidoAdmin,
    EventoPedido,
    ListaPedidosAdmin,
    PedidoAdmin,
    Resolucion,
    TotalesGanancia,
)
from app.services import recarga_service
from app.services.codigos import id_desde_codigo
from app.services.consultas_pedidos import (
    POR_PAGINA,
    POR_PAGINA_MAXIMO,
    FiltrosPedidoAdmin,
    paginar,
)
from app.services.estados import Estado, TransicionInvalida
from app.services.recarga_service import ErrorResolucion

router = APIRouter(prefix="/pedidos")

MENSAJE_NO_ENCONTRADO = "Pedido no encontrado."


def _consulta():
    return (
        select(Pedido, Usuario.usuario, Paquete.nombre)
        .join(Usuario, Usuario.id == Pedido.usuario_id)
        .join(Paquete, Paquete.paquete_id == Pedido.paquete_id)
    )


def _pedido_admin(pedido: Pedido, usuario: str, paquete: str) -> dict:
    exitoso = pedido.estado == Estado.EXITOSO
    return {
        "id": pedido.id,
        "codigo": pedido.codigo,
        "fecha": pedido.creado_en,
        "actualizado_en": pedido.actualizado_en,
        "usuario_id": pedido.usuario_id,
        "usuario": usuario,
        "paquete_id": pedido.paquete_id,
        "paquete": paquete,
        "player_id": pedido.player_id,
        "nickname": pedido.nickname,
        "precio_venta": pedido.precio_venta,
        "precio_costo": pedido.precio_costo,
        "ganancia": pedido.precio_venta - pedido.precio_costo if exitoso else None,
        "estado": pedido.estado,
        "referencia": pedido.referencia,
        "error": pedido.error,
        "error_code": pedido.error_code,
    }


def _id_pedido(pedido: str) -> int | None:
    """Acepta el id numérico o el código `FF-000123`."""
    pedido = pedido.strip()
    return int(pedido) if pedido.isdecimal() else id_desde_codigo(pedido)


@router.get("", response_model=ListaPedidosAdmin)
async def listar(
    bd: Bd,
    estado: Estado | None = None,
    desde: datetime | None = None,
    hasta: datetime | None = None,
    player_id: str | None = None,
    codigo: str | None = None,
    usuario: str | None = None,
    referencia: str | None = None,
    solo_pendientes: bool = False,
    pagina: Annotated[int, Query(ge=1)] = 1,
    por_pagina: Annotated[int, Query(ge=1, le=POR_PAGINA_MAXIMO)] = POR_PAGINA,
):
    """Listado con filtros (RF-50, CA-06) y totales de ganancia del filtro (RF-54)."""
    filtros = FiltrosPedidoAdmin(
        estado, desde, hasta, player_id, codigo, usuario, referencia, solo_pendientes
    )
    resultado = await paginar(bd, filtros.aplicar(_consulta()), pagina, por_pagina)

    exitosos = filtros.aplicar(
        select(Pedido.precio_venta, Pedido.precio_costo)
        .join(Usuario, Usuario.id == Pedido.usuario_id)
        .where(Pedido.estado == Estado.EXITOSO)
    ).subquery()
    cantidad, venta, costo = (
        await bd.execute(
            select(
                func.count(),
                func.coalesce(func.sum(exitosos.c.precio_venta), 0),
                func.coalesce(func.sum(exitosos.c.precio_costo), 0),
            )
        )
    ).one()
    return ListaPedidosAdmin(
        pedidos=[PedidoAdmin(**_pedido_admin(*fila)) for fila in resultado.filas],
        total=resultado.total,
        pagina=resultado.pagina,
        por_pagina=resultado.por_pagina,
        totales=TotalesGanancia(
            exitosos=cantidad, venta=venta, costo=costo, ganancia=venta - costo
        ),
    )


@router.get("/{pedido}", response_model=DetallePedidoAdmin)
async def detalle(pedido: str, bd: Bd):
    """Todos los datos, costo, venta, ganancia e historial de estados (RF-51)."""
    pedido_id = _id_pedido(pedido)
    fila = None
    if pedido_id is not None:
        fila = (await bd.execute(_consulta().where(Pedido.id == pedido_id))).first()
    if fila is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, MENSAJE_NO_ENCONTRADO)
    eventos = await bd.scalars(
        select(PedidoEvento)
        .where(PedidoEvento.pedido_id == pedido_id)
        .order_by(PedidoEvento.fecha, PedidoEvento.id)
    )
    return DetallePedidoAdmin(
        **_pedido_admin(*fila), eventos=[EventoPedido.model_validate(e) for e in eventos]
    )


@router.post("/{pedido}/resolver", response_model=DetallePedidoAdmin)
async def resolver(pedido: str, datos: Resolucion, request: Request, actual: Admin, bd: Bd):
    """Marca un PENDIENTE_VERIFICAR como exitoso o fallido (RF-52, RN-04, RF-55)."""
    pedido_id = _id_pedido(pedido)
    if pedido_id is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, MENSAJE_NO_ENCONTRADO)
    try:
        await recarga_service.resolver_pendiente(
            bd,
            pedido_id,
            datos.resultado,
            admin_id=actual.usuario_id,
            nota=datos.nota,
            referencia=datos.referencia,
            ip=ip_cliente(request),
        )
    except LookupError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, MENSAJE_NO_ENCONTRADO) from None
    except TransicionInvalida:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Solo se resuelven pedidos en revisión."
        ) from None
    except ErrorResolucion as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(error)) from None
    return await detalle(str(pedido_id), bd)
