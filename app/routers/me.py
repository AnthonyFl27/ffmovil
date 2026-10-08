"""Datos del propio cliente: resumen, fondos e historial (RF-31 a RF-36)."""

from fastapi import APIRouter
from sqlalchemy import func, select

from app.models import Movimiento, Pedido, Saldo
from app.routers.dependencias import Bd, Cliente
from app.schemas.cliente import Fondos, MovimientoFondos, Resumen
from app.services.estados import Estado

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
