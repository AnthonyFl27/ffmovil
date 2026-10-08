"""Páginas del cliente: inicio, recargar, historial y fondos (RF-20 a RF-36).

Cada página llama a la ruta JSON correspondiente y renderiza su esquema de
cliente, que no tiene `precio_costo` (RF-35, CA-03).
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Form, HTTPException, Request, Response, status

from app.routers import me, paquetes, recargas
from app.routers.dependencias import Bd
from app.schemas.cliente import SolicitudRecarga, SolicitudValidacion
from app.services.estados import ESTADOS_FINALES, ETIQUETAS_CLIENTE, Estado
from app.web import filtros
from app.web.plantillas import ClienteWeb, ErrorWeb, error, es_htmx, es_parcial, render

router = APIRouter(include_in_schema=False)

MENSAJE_PAQUETE = "Elige un paquete disponible."
# Segundos entre consultas de un pedido en proceso.
INTERVALO_CONSULTA = 3

# Opciones del filtro de estado (spec sec. 7): Procesando agrupa CREADO y PROCESANDO.
OPCIONES_ESTADO = [
    (Estado.PROCESANDO, ETIQUETAS_CLIENTE[Estado.PROCESANDO]),
    (Estado.EXITOSO, ETIQUETAS_CLIENTE[Estado.EXITOSO]),
    (Estado.FALLIDO, ETIQUETAS_CLIENTE[Estado.FALLIDO]),
    (Estado.PENDIENTE_VERIFICAR, ETIQUETAS_CLIENTE[Estado.PENDIENTE_VERIFICAR]),
]


@router.get("/inicio")
async def inicio(request: Request, actual: ClienteWeb, bd: Bd):
    """Saldo disponible, gasto total y nº de recargas exitosas (RF-33)."""
    resumen = await me.resumen(actual, bd)
    return render(request, "cliente/inicio.html", actual, resumen=resumen)


@router.get("/fondos")
async def fondos(request: Request, actual: ClienteWeb, bd: Bd):
    """Saldo disponible, reservado y abonos y ajustes con su nota (RF-34)."""
    datos = await me.fondos(actual, bd)
    return render(request, "cliente/fondos.html", actual, fondos=datos)


# --- Recargar (RF-20, RF-21, RF-25) -------------------------------------------------


@router.get("/recargar")
async def recargar(request: Request, actual: ClienteWeb, bd: Bd):
    lista = await paquetes.paquetes(actual, bd)
    resumen = await me.resumen(actual, bd)
    return render(request, "cliente/recargar.html", actual, paquetes=lista, resumen=resumen)


def _paquete_id(valor: str) -> int:
    try:
        return int(valor)
    except ValueError:
        raise ErrorWeb(MENSAJE_PAQUETE, status.HTTP_422_UNPROCESSABLE_CONTENT) from None


@router.post("/recargar/validar")
async def recargar_validar(
    request: Request,
    actual: ClienteWeb,
    bd: Bd,
    player_id: Annotated[str, Form()] = "",
    paquete_id: Annotated[str, Form()] = "",
):
    """Valida el ID y muestra la confirmación con un token de idempotencia nuevo (RF-20)."""
    datos = SolicitudValidacion(player_id=player_id, paquete_id=_paquete_id(paquete_id))
    try:
        validacion = await recargas.validar(datos, request, actual, bd)
    except HTTPException as fallo:
        return error(request, fallo.detail, fallo.status_code)
    paquete = next(
        (p for p in await paquetes.paquetes(actual, bd) if p.paquete_id == datos.paquete_id),
        None,
    )
    if paquete is None:
        return error(request, MENSAJE_PAQUETE, status.HTTP_422_UNPROCESSABLE_CONTENT)
    resumen = await me.resumen(actual, bd)
    return render(
        request,
        "cliente/_confirmacion.html",
        actual,
        player_id=player_id.strip(),
        paquete=paquete,
        validacion=validacion,
        resumen=resumen,
        token=uuid.uuid4().hex,
    )


@router.post("/recargar/confirmar")
async def recargar_confirmar(
    request: Request,
    actual: ClienteWeb,
    bd: Bd,
    player_id: Annotated[str, Form()] = "",
    paquete_id: Annotated[str, Form()] = "",
    token_idempotencia: Annotated[str, Form()] = "",
    confirmar_sin_verificar: Annotated[str, Form()] = "",
):
    """Crea la recarga (RF-21, RF-25); el mismo token devuelve el mismo pedido (CA-02)."""
    datos = SolicitudRecarga(
        paquete_id=_paquete_id(paquete_id),
        player_id=player_id,
        token_idempotencia=token_idempotencia,
        confirmar_sin_verificar=bool(confirmar_sin_verificar),
    )
    try:
        pedido = await recargas.crear_recarga(datos, request, Response(), actual, bd)
    except HTTPException as fallo:
        return error(request, fallo.detail, fallo.status_code)
    return _fragmento_pedido(request, actual, pedido)


def _fragmento_pedido(request: Request, actual, pedido) -> Response:
    en_proceso = Estado(pedido.estado) not in ESTADOS_FINALES | {Estado.PENDIENTE_VERIFICAR}
    return render(
        request,
        "cliente/_pedido.html",
        actual,
        pedido=pedido,
        en_proceso=en_proceso,
        intervalo=INTERVALO_CONSULTA,
    )


# --- Historial (RF-30 a RF-32, CA-05) -----------------------------------------------


@router.get("/historial")
async def historial(
    request: Request,
    actual: ClienteWeb,
    bd: Bd,
    estado: str | None = None,
    desde: str | None = None,
    hasta: str | None = None,
    tz: str | None = None,
    player_id: str | None = None,
    codigo: str | None = None,
    pagina: str | None = None,
):
    inicio, fin = filtros.rango_utc(desde, hasta, tz)
    lista = await me.pedidos(
        actual,
        bd,
        estado=filtros.estado(estado),
        desde=inicio,
        hasta=fin,
        player_id=filtros.texto(player_id),
        codigo=filtros.texto(codigo),
        pagina=filtros.pagina(pagina),
        por_pagina=me.POR_PAGINA,
    )
    valores = {
        "estado": estado,
        "desde": desde,
        "hasta": hasta,
        "tz": tz,
        "player_id": player_id,
        "codigo": codigo,
    }
    plantilla = (
        "cliente/_tabla_pedidos.html"
        if es_parcial(request, "pedidos")
        else "cliente/historial.html"
    )
    return render(
        request,
        plantilla,
        actual,
        lista=lista,
        filtros=valores,
        consulta=filtros.consulta,
        opciones_estado=OPCIONES_ESTADO,
    )


@router.get("/historial/{codigo}")
async def historial_pedido(codigo: str, request: Request, actual: ClienteWeb, bd: Bd):
    """Detalle de un pedido propio; con HTMX devuelve solo el fragmento (consulta periódica)."""
    try:
        pedido = await me.pedido(codigo, actual, bd)
    except HTTPException as fallo:
        raise ErrorWeb(fallo.detail, fallo.status_code) from None
    if es_htmx(request):
        return _fragmento_pedido(request, actual, pedido)
    return render(request, "cliente/pedido.html", actual, pedido=pedido)
