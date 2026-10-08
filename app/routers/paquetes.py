"""Catálogo visible para el cliente (RF-13)."""

from fastapi import APIRouter
from sqlalchemy import select

from app.models import Paquete
from app.models.catalogo import JUEGO_FREE_FIRE
from app.routers.dependencias import Bd, Cliente
from app.schemas.cliente import PaqueteCliente

router = APIRouter(tags=["cliente"])


@router.get("/paquetes", response_model=list[PaqueteCliente])
async def paquetes(actual: Cliente, bd: Bd):
    """Solo paquetes activos con su `precio_venta`; nunca el costo (RF-13, RF-35)."""
    consulta = (
        select(Paquete)
        .where(
            Paquete.activo.is_(True),
            Paquete.precio_venta.is_not(None),
            Paquete.juego == JUEGO_FREE_FIRE,
        )
        .order_by(Paquete.precio_venta, Paquete.paquete_id)
    )
    return [PaqueteCliente.model_validate(p) for p in await bd.scalars(consulta)]
