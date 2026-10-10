"""Catálogo: precios de venta, activación y sincronización con VentasFF (RF-10 a RF-14).

El `precio_venta` lo fija el admin a mano; no hay cálculo de margen (RF-11).
Ninguna función hace commit: corren en la transacción de quien las llama.
"""

import logging
from dataclasses import dataclass, field
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Paquete
from app.models.catalogo import JUEGO_FREE_FIRE
from app.services import montos
from app.services.ventasff_client import ClienteVentasFF

logger = logging.getLogger(__name__)


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


@dataclass(frozen=True)
class ResumenSincronizacion:
    recibidos: int = 0
    nuevos: int = 0
    actualizados: int = 0
    desactivados: int = 0
    # Paquetes con precio de venta <= costo tras la sincronización (RF-14).
    bajo_costo: list[int] = field(default_factory=list)
    # La respuesta no traía ningún paquete free_fire: no se tocó el catálogo (RF-10, CHG-018).
    catalogo_vacio: bool = False


async def sincronizar_catalogo(
    sesion: AsyncSession, cliente: ClienteVentasFF
) -> ResumenSincronizacion:
    """Sincroniza `productos.php` con la tabla `paquetes` (RF-10, RF-14).

    Solo `free_fire`. Actualiza nombre, diamantes y costo; los nuevos se crean
    inactivos y sin precio de venta; los que ya no vienen se desactivan. Nunca
    modifica `precio_venta`. Si la API falla, propaga el error sin cambios. Si no llega
    ningún paquete `free_fire` no toca nada y devuelve `catalogo_vacio=True`.
    """
    productos = {p.paquete_id: p for p in await cliente.productos() if p.juego == JUEGO_FREE_FIRE}
    if not productos:
        logger.warning(
            "Catálogo vacío: VentasFF no devolvió paquetes %s; no se modifica", JUEGO_FREE_FIRE
        )
        return ResumenSincronizacion(catalogo_vacio=True)

    existentes = {
        p.paquete_id: p
        for p in await sesion.scalars(
            select(Paquete).with_for_update().execution_options(populate_existing=True)
        )
    }
    nuevos = actualizados = desactivados = 0
    for paquete_id, producto in productos.items():
        paquete = existentes.get(paquete_id)
        if paquete is None:
            sesion.add(
                Paquete(
                    paquete_id=paquete_id,
                    juego=producto.juego,
                    nombre=producto.nombre,
                    diamantes=producto.diamantes,
                    precio_costo=producto.precio,
                    precio_venta=None,
                    activo=False,
                )
            )
            nuevos += 1
            continue
        datos = (producto.nombre, producto.diamantes, producto.precio)
        if (paquete.nombre, paquete.diamantes, paquete.precio_costo) != datos:
            paquete.nombre, paquete.diamantes, paquete.precio_costo = datos
            paquete.actualizado_en = func.now()
            actualizados += 1

    for paquete_id, paquete in existentes.items():
        if paquete_id not in productos and paquete.activo:
            paquete.activo = False
            paquete.actualizado_en = func.now()
            desactivados += 1

    await sesion.flush()
    bajo_costo = sorted(
        p.paquete_id
        for p in existentes.values()
        if p.paquete_id in productos and precio_bajo_costo(p)
    )
    resumen = ResumenSincronizacion(len(productos), nuevos, actualizados, desactivados, bajo_costo)
    logger.info("Catálogo sincronizado: %s", resumen)
    if bajo_costo:
        logger.warning("Paquetes con precio de venta <= costo: %s", bajo_costo)
    return resumen
