"""Catálogo: precios de venta, activación y sincronización con VentasFF (RF-10 a RF-14).

El `precio_venta` lo fija el admin a mano; no hay cálculo de margen (RF-11).
Ninguna función hace commit: corren en la transacción de quien las llama.
"""

from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Paquete
from app.services import montos


class ErrorCatalogo(Exception):
    pass


class PrecioInvalido(ErrorCatalogo):
    pass


class PaqueteInexistente(ErrorCatalogo):
    pass


class PaqueteSinPrecio(ErrorCatalogo):
    """Un paquete sin `precio_venta` no puede activarse (RF-11)."""


@dataclass(frozen=True)
class ResultadoPrecio:
    paquete: Paquete
    # Aviso al admin: el precio de venta no supera al de costo (RF-12).
    bajo_costo: bool


def validar_precio_venta(precio: Decimal) -> Decimal:
    """Decimal > 0 con 2 decimales como máximo (RNF-04)."""
    try:
        return montos.normalizar_monto(precio)
    except montos.MontoInvalido as error:
        raise PrecioInvalido(f"Precio de venta inválido: {error}") from None


def precio_bajo_costo(paquete: Paquete) -> bool:
    """True si tiene precio de venta y es <= al de costo (RF-12, RF-14)."""
    return paquete.precio_venta is not None and paquete.precio_venta <= paquete.precio_costo


async def _bloquear(sesion: AsyncSession, paquete_id: int) -> Paquete:
    paquete = await sesion.scalar(
        select(Paquete)
        .where(Paquete.paquete_id == paquete_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if paquete is None:
        raise PaqueteInexistente(f"No existe el paquete {paquete_id}")
    return paquete


async def fijar_precio_venta(
    sesion: AsyncSession, paquete_id: int, precio: Decimal
) -> ResultadoPrecio:
    """Define o cambia el precio de venta; avisa si no supera al de costo (RF-12)."""
    precio = validar_precio_venta(precio)
    paquete = await _bloquear(sesion, paquete_id)
    paquete.precio_venta = precio
    paquete.actualizado_en = func.now()
    await sesion.flush()
    await sesion.refresh(paquete)
    return ResultadoPrecio(paquete, precio_bajo_costo(paquete))


async def activar(sesion: AsyncSession, paquete_id: int) -> Paquete:
    paquete = await _bloquear(sesion, paquete_id)
    if paquete.precio_venta is None:
        raise PaqueteSinPrecio("Define el precio de venta antes de activar el paquete")
    paquete.activo = True
    await sesion.flush()
    return paquete


async def desactivar(sesion: AsyncSession, paquete_id: int) -> Paquete:
    paquete = await _bloquear(sesion, paquete_id)
    paquete.activo = False
    await sesion.flush()
    return paquete
