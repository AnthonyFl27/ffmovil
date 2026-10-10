"""Catálogo para el admin: precios, activación y sincronización (RF-10 a RF-12, RF-14, RF-55)."""

import json

from fastapi import APIRouter, HTTPException, Request, status
from sqlalchemy import select

from app.models import Config, Paquete
from app.routers.dependencias import Admin, Bd, ip_cliente
from app.schemas.admin import CambioPaquete, Catalogo, PaqueteAdmin
from app.services import auditoria, catalogo
from app.services.catalogo import ErrorCatalogo, PaqueteInexistente, precio_bajo_costo
from app.services.tareas import CLAVE_ULTIMA_SINCRONIZACION, ejecutar_sincronizacion

router = APIRouter()

MENSAJE_SINCRONIZACION = "No se pudo sincronizar con VentasFF. Revisa el resultado en el catálogo."


def _paquete_admin(paquete: Paquete) -> PaqueteAdmin:
    return PaqueteAdmin.model_validate(paquete).model_copy(
        update={"bajo_costo": precio_bajo_costo(paquete)}
    )


async def _catalogo(bd: Bd) -> Catalogo:
    paquetes = await bd.scalars(
        select(Paquete)
        .order_by(Paquete.juego, Paquete.precio_costo, Paquete.paquete_id)
        .execution_options(populate_existing=True)
    )
    ultima = await bd.scalar(
        select(Config.valor).where(Config.clave == CLAVE_ULTIMA_SINCRONIZACION)
    )
    return Catalogo(
        paquetes=[_paquete_admin(p) for p in paquetes],
        ultima_sincronizacion=json.loads(ultima) if ultima else None,
    )


@router.get("/paquetes", response_model=Catalogo)
async def listar(bd: Bd):
    """Todos los paquetes con costo; marca los de precio de venta <= costo (RF-14)."""
    return await _catalogo(bd)


@router.put("/paquetes/{paquete_id}", response_model=PaqueteAdmin)
async def editar(paquete_id: int, datos: CambioPaquete, request: Request, actual: Admin, bd: Bd):
    """Fija `precio_venta` y/o activa o desactiva (RF-11, RF-12). `bajo_costo` es el aviso."""
    try:
        anterior = await bd.get(Paquete, paquete_id)
        if anterior is None:
            raise PaqueteInexistente("Paquete no encontrado.")
        detalle = {"paquete_id": paquete_id}
        if datos.precio_venta is not None:
            detalle["precio_anterior"] = (
                f"{anterior.precio_venta:.2f}" if anterior.precio_venta is not None else None
            )
            resultado = await catalogo.fijar_precio_venta(bd, paquete_id, datos.precio_venta)
            detalle["precio_venta"] = f"{resultado.paquete.precio_venta:.2f}"
        if datos.activo is True:
            await catalogo.activar(bd, paquete_id)
        elif datos.activo is False:
            await catalogo.desactivar(bd, paquete_id)
        if datos.activo is not None:
            detalle["activo"] = datos.activo
    except PaqueteInexistente:
        await bd.rollback()
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Paquete no encontrado.") from None
    except ErrorCatalogo as error:
        await bd.rollback()
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(error)) from None
    auditoria.registrar(bd, actual.usuario_id, "editar_paquete", detalle, ip_cliente(request))
    await bd.commit()
    paquete = await bd.get(Paquete, paquete_id, populate_existing=True)
    return _paquete_admin(paquete)


def _resultado_auditado(resumen) -> str:
    if resumen is None:
        return "error"
    return "vacio" if resumen.catalogo_vacio else "ok"


@router.post("/catalogo/sincronizar", response_model=Catalogo)
async def sincronizar(request: Request, actual: Admin, bd: Bd):
    """Sincroniza `productos.php` ahora (RF-10); nunca cambia `precio_venta` (RF-14)."""
    app = request.app
    resumen = await ejecutar_sincronizacion(app.state.sesiones, app.state.crear_cliente_ventasff)
    auditoria.registrar(
        bd,
        actual.usuario_id,
        "sincronizar_catalogo",
        {"resultado": _resultado_auditado(resumen)},
        ip_cliente(request),
    )
    await bd.commit()
    if resumen is None:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, MENSAJE_SINCRONIZACION)
    return await _catalogo(bd)
