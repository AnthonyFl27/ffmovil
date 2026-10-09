"""Páginas del admin: panel, usuarios y saldos, pedidos, catálogo, config y auditoría.

Llaman a las rutas JSON de `/admin/*` (RF-03, RF-12, RF-40, RF-41, RF-50 a RF-55,
RN-10, RN-11), que validan, auditan y confirman las transacciones.
"""

from typing import Annotated

from fastapi import APIRouter, Form, HTTPException, Request, status
from pydantic import ValidationError

from app.routers.admin import auditoria, catalogo, panel, pedidos, saldos, usuarios
from app.routers.dependencias import Bd
from app.schemas.admin import (
    CambioPaquete,
    ConfigAdmin,
    MovimientoSaldo,
    NuevoUsuario,
    Resolucion,
)
from app.services.consultas_pedidos import POR_PAGINA
from app.services.estados import Estado
from app.web import filtros
from app.web.plantillas import AdminWeb, ErrorWeb, error, es_parcial, render

router = APIRouter(prefix="/gestion", include_in_schema=False)

MENSAJE_MONTO = "Monto inválido. Usa un número con hasta 2 decimales."
MENSAJE_USUARIO = "Usuario no encontrado."
MENSAJE_RESOLUCION = "Elige si la recarga fue exitosa o fallida."
# Elementos donde se muestran los errores de formularios que reemplazan otra parte.
MENSAJE_RESOLVER = "#mensaje-resolucion"
MENSAJE_CATALOGO = "#mensaje-catalogo"
OPCIONES_ESTADO = [(e, e.value) for e in Estado if e != Estado.CREADO]


def _rechazo(request: Request, fallo: HTTPException, destino: str | None = None):
    return error(request, fallo.detail, fallo.status_code, destino)


# --- Panel y alertas (RF-53, RF-54, RN-10, RN-11) ------------------------------------


@router.get("")
async def inicio(request: Request, actual: AdminWeb, bd: Bd):
    datos = await panel.panel(request, bd)
    return render(request, "admin/panel.html", actual, panel=datos)


@router.post("/alertas/{alerta_id}/atender")
async def atender_alerta(alerta_id: int, request: Request, actual: AdminWeb, bd: Bd):
    try:
        await panel.atender(alerta_id, request, actual, bd)
    except HTTPException as fallo:
        return _rechazo(request, fallo)
    activas = await panel.listar_alertas(bd)
    return render(request, "admin/_alertas.html", actual, alertas=activas)


# --- Usuarios y saldos (RF-03, RF-40, RF-41) ----------------------------------------


@router.get("/usuarios")
async def lista_usuarios(request: Request, actual: AdminWeb, bd: Bd):
    lista = await usuarios.listar(bd)
    return render(request, "admin/usuarios.html", actual, usuarios=lista)


@router.post("/usuarios")
async def crear_usuario(
    request: Request, actual: AdminWeb, bd: Bd, usuario: Annotated[str, Form()] = ""
):
    """Crea un cliente; la clave temporal se muestra una sola vez (RF-02, RF-03)."""
    try:
        creado = await usuarios.crear(NuevoUsuario(usuario=usuario), request, actual, bd)
    except HTTPException as fallo:
        return _rechazo(request, fallo)
    lista = await usuarios.listar(bd)
    return render(request, "admin/_usuario_creado.html", actual, creado=creado, usuarios=lista)


async def _usuario(bd: Bd, usuario_id: int):
    encontrado = next((u for u in await usuarios.listar(bd) if u.id == usuario_id), None)
    if encontrado is None:
        raise ErrorWeb(MENSAJE_USUARIO, status.HTTP_404_NOT_FOUND)
    return encontrado


@router.get("/usuarios/{usuario_id}")
async def ver_usuario(usuario_id: int, request: Request, actual: AdminWeb, bd: Bd):
    datos = await _usuario(bd, usuario_id)
    return render(request, "admin/usuario.html", actual, u=datos, clave_temporal=None)


@router.post("/usuarios/{usuario_id}/{accion}")
async def accion_usuario(usuario_id: int, accion: str, request: Request, actual: AdminWeb, bd: Bd):
    """Bloquear, desbloquear o resetear la clave (RF-03, RF-06)."""
    operaciones = {
        "bloquear": usuarios.bloquear,
        "desbloquear": usuarios.desbloquear,
        "reset-clave": usuarios.resetear_clave,
    }
    if accion not in operaciones:
        raise ErrorWeb("Acción no válida.", status.HTTP_404_NOT_FOUND)
    try:
        resultado = await operaciones[accion](usuario_id, request, actual, bd)
    except HTTPException as fallo:
        return _rechazo(request, fallo)
    if accion == "reset-clave":
        datos, clave = resultado.usuario, resultado.clave_temporal
    else:
        datos, clave = resultado, None
    return render(request, "admin/_usuario.html", actual, u=datos, clave_temporal=clave)


@router.post("/usuarios/{usuario_id}/saldo/{tipo}")
async def mover_saldo(
    usuario_id: int,
    tipo: str,
    request: Request,
    actual: AdminWeb,
    bd: Bd,
    monto: Annotated[str, Form()] = "",
    nota: Annotated[str, Form()] = "",
    sentido: Annotated[str | None, Form()] = None,
):
    """Abono o ajuste con nota obligatoria (RF-40, RF-41).

    En el ajuste, `sentido` (sumar/restar) indica el signo; el monto se escribe sin signo.
    """
    if tipo not in ("abono", "ajuste"):
        raise ErrorWeb("Acción no válida.", status.HTTP_404_NOT_FOUND)
    monto = monto.strip()
    if tipo == "ajuste" and sentido in ("sumar", "restar"):
        monto = monto.lstrip("+-").strip()
        if sentido == "restar":
            monto = f"-{monto}"
    try:
        datos = MovimientoSaldo(monto=monto, nota=nota)
    except ValidationError:
        return error(request, MENSAJE_MONTO, status.HTTP_422_UNPROCESSABLE_CONTENT)
    operacion = saldos.abonar if tipo == "abono" else saldos.ajustar
    try:
        movimiento = await operacion(usuario_id, datos, request, actual, bd)
    except HTTPException as fallo:
        return _rechazo(request, fallo)
    usuario = await _usuario(bd, usuario_id)
    return render(request, "admin/_saldo_movido.html", actual, movimiento=movimiento, u=usuario)


# --- Pedidos (RF-50 a RF-52, RF-54, CA-06) ------------------------------------------


@router.get("/pedidos")
async def lista_pedidos(
    request: Request,
    actual: AdminWeb,
    bd: Bd,
    estado: str | None = None,
    desde: str | None = None,
    hasta: str | None = None,
    tz: str | None = None,
    usuario: str | None = None,
    player_id: str | None = None,
    codigo: str | None = None,
    referencia: str | None = None,
    solo_pendientes: str | None = None,
    pagina: str | None = None,
):
    inicio, fin = filtros.rango_utc(desde, hasta, tz)
    lista = await pedidos.listar(
        bd,
        estado=filtros.estado(estado),
        desde=inicio,
        hasta=fin,
        player_id=filtros.texto(player_id),
        codigo=filtros.texto(codigo),
        usuario=filtros.texto(usuario),
        referencia=filtros.texto(referencia),
        solo_pendientes=bool(solo_pendientes),
        pagina=filtros.pagina(pagina),
        por_pagina=POR_PAGINA,
    )
    valores = {
        "estado": estado,
        "desde": desde,
        "hasta": hasta,
        "tz": tz,
        "usuario": usuario,
        "player_id": player_id,
        "codigo": codigo,
        "referencia": referencia,
        "solo_pendientes": solo_pendientes,
    }
    plantilla = (
        "admin/_tabla_pedidos.html" if es_parcial(request, "pedidos") else "admin/pedidos.html"
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


@router.get("/pedidos/{pedido}")
async def ver_pedido(pedido: str, request: Request, actual: AdminWeb, bd: Bd):
    try:
        detalle = await pedidos.detalle(pedido, bd)
    except HTTPException as fallo:
        raise ErrorWeb(fallo.detail, fallo.status_code) from None
    return render(request, "admin/pedido.html", actual, pedido=detalle)


@router.post("/pedidos/{pedido}/resolver")
async def resolver_pedido(
    pedido: str,
    request: Request,
    actual: AdminWeb,
    bd: Bd,
    resultado: Annotated[str, Form()] = "",
    nota: Annotated[str, Form()] = "",
    referencia: Annotated[str, Form()] = "",
):
    """Marca un pedido en revisión como exitoso o fallido (RF-52)."""
    try:
        datos = Resolucion(resultado=resultado, nota=nota, referencia=referencia.strip() or None)
    except ValidationError:
        return error(
            request, MENSAJE_RESOLUCION, status.HTTP_422_UNPROCESSABLE_CONTENT, MENSAJE_RESOLVER
        )
    try:
        detalle = await pedidos.resolver(pedido, datos, request, actual, bd)
    except HTTPException as fallo:
        return _rechazo(request, fallo, MENSAJE_RESOLVER)
    return render(request, "admin/_detalle_pedido.html", actual, pedido=detalle)


# --- Catálogo (RF-10 a RF-12, RF-14) ------------------------------------------------


@router.get("/paquetes")
async def lista_paquetes(request: Request, actual: AdminWeb, bd: Bd):
    datos = await catalogo.listar(bd)
    return render(request, "admin/paquetes.html", actual, catalogo=datos)


@router.post("/paquetes/{paquete_id}")
async def editar_paquete(
    paquete_id: int,
    request: Request,
    actual: AdminWeb,
    bd: Bd,
    precio_venta: Annotated[str, Form()] = "",
    activo: Annotated[str, Form()] = "",
):
    """Fija el precio de venta y/o activa o desactiva; avisa si queda bajo costo (RF-12)."""
    try:
        cambio = CambioPaquete(
            precio_venta=precio_venta.strip() or None,
            activo={"si": True, "no": False}.get(activo),
        )
    except ValidationError:
        return error(
            request, MENSAJE_MONTO, status.HTTP_422_UNPROCESSABLE_CONTENT, MENSAJE_CATALOGO
        )
    try:
        paquete = await catalogo.editar(paquete_id, cambio, request, actual, bd)
    except HTTPException as fallo:
        return _rechazo(request, fallo, MENSAJE_CATALOGO)
    return render(request, "admin/_fila_paquete.html", actual, p=paquete, guardado=True)


@router.post("/catalogo/sincronizar")
async def sincronizar(request: Request, actual: AdminWeb, bd: Bd):
    """Sincroniza ahora con `productos.php` (RF-10)."""
    try:
        datos = await catalogo.sincronizar(request, actual, bd)
    except HTTPException as fallo:
        return _rechazo(request, fallo, MENSAJE_CATALOGO)
    return render(request, "admin/_catalogo.html", actual, catalogo=datos, sincronizado=True)


# --- Configuración y auditoría (RN-11, RF-55) ---------------------------------------


@router.get("/config")
async def ver_config(request: Request, actual: AdminWeb, bd: Bd):
    datos = await panel.ver_config(bd)
    return render(request, "admin/config.html", actual, config=datos)


@router.post("/config")
async def guardar_config(
    request: Request, actual: AdminWeb, bd: Bd, alerta_credito_min: Annotated[str, Form()] = ""
):
    try:
        datos = ConfigAdmin(alerta_credito_min=alerta_credito_min.strip())
    except ValidationError:
        return error(request, MENSAJE_MONTO, status.HTTP_422_UNPROCESSABLE_CONTENT)
    await panel.cambiar_config(datos, request, actual, bd)
    return render(
        request, "parciales/exito.html", actual, mensaje="Umbral de crédito bajo guardado."
    )


@router.get("/auditoria")
async def ver_auditoria(
    request: Request,
    actual: AdminWeb,
    bd: Bd,
    accion: str | None = None,
    desde: str | None = None,
    hasta: str | None = None,
    tz: str | None = None,
    pagina: str | None = None,
):
    inicio, fin = filtros.rango_utc(desde, hasta, tz)
    lista = await auditoria.listar(
        bd,
        accion=filtros.texto(accion),
        usuario_id=None,
        desde=inicio,
        hasta=fin,
        pagina=filtros.pagina(pagina),
        por_pagina=POR_PAGINA,
    )
    valores = {"accion": accion, "desde": desde, "hasta": hasta, "tz": tz}
    plantilla = (
        "admin/_tabla_auditoria.html"
        if es_parcial(request, "registros")
        else "admin/auditoria.html"
    )
    return render(
        request, plantilla, actual, lista=lista, filtros=valores, consulta=filtros.consulta
    )
