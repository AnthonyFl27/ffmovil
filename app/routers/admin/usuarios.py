"""Gestión de usuarios por el admin (RF-03, RF-06, RF-07, RF-55)."""

from datetime import datetime
from typing import Annotated, Literal

from fastapi import APIRouter, HTTPException, Query, Request, status
from sqlalchemy import func, select
from sqlalchemy.orm import aliased

from app.models import Movimiento, Pedido, Saldo, Usuario
from app.routers.dependencias import Admin, Bd, ip_cliente
from app.schemas.admin import (
    ListaMovimientos,
    MovimientoUsuario,
    NuevoUsuario,
    UsuarioAdmin,
    UsuarioConClave,
)
from app.services import auditoria, auth_service, sesiones
from app.services.auth_service import DatosUsuarioInvalidos, UsuarioDuplicado
from app.services.consultas_pedidos import POR_PAGINA, POR_PAGINA_MAXIMO, utc

router = APIRouter(prefix="/usuarios")

MENSAJE_NO_ENCONTRADO = "Usuario no encontrado."
MENSAJE_BLOQUEARSE = "No puedes bloquear tu propia cuenta."
REGISTRADO_POR_SISTEMA = "sistema"
# Tipos que salen de la cuenta o pasan a reservado se muestran en negativo (RF-43).
TIPOS_QUE_RESTAN = ("reserva", "cargo")


def _usuario_admin(usuario: Usuario, saldo: Saldo | None) -> UsuarioAdmin:
    return UsuarioAdmin(
        id=usuario.id,
        usuario=usuario.usuario,
        rol=usuario.rol,
        activo=usuario.activo,
        debe_cambiar_clave=usuario.debe_cambiar_clave,
        creado_en=usuario.creado_en,
        ultimo_login=usuario.ultimo_login,
        saldo_disponible=saldo.saldo_disponible if saldo else None,
        saldo_reservado=saldo.saldo_reservado if saldo else None,
    )


async def _bloquear_usuario(bd: Bd, usuario_id: int) -> tuple[Usuario, Saldo | None]:
    fila = (
        await bd.execute(
            select(Usuario, Saldo)
            .outerjoin(Saldo, Saldo.usuario_id == Usuario.id)
            .where(Usuario.id == usuario_id)
            .with_for_update(of=Usuario)
            .execution_options(populate_existing=True)
        )
    ).first()
    if fila is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, MENSAJE_NO_ENCONTRADO)
    return fila.Usuario, fila.Saldo


@router.get("", response_model=list[UsuarioAdmin])
async def listar(bd: Bd):
    filas = await bd.execute(
        select(Usuario, Saldo)
        .outerjoin(Saldo, Saldo.usuario_id == Usuario.id)
        .order_by(Usuario.usuario)
    )
    return [_usuario_admin(u, s) for u, s in filas]


@router.post("", response_model=UsuarioConClave, status_code=status.HTTP_201_CREATED)
async def crear(datos: NuevoUsuario, request: Request, actual: Admin, bd: Bd):
    """Crea un cliente con clave temporal (RF-02, RF-03); los admins se crean por CLI."""
    try:
        usuario, clave = await auth_service.crear_usuario(bd, datos.usuario, rol="cliente")
    except UsuarioDuplicado as error:
        raise HTTPException(status.HTTP_409_CONFLICT, str(error)) from None
    except DatosUsuarioInvalidos as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(error)) from None
    auditoria.registrar(
        bd,
        actual.usuario_id,
        "crear_usuario",
        {"usuario_id": usuario.id, "usuario": usuario.usuario},
        ip_cliente(request),
    )
    await bd.commit()
    await bd.refresh(usuario)
    saldo = await bd.get(Saldo, usuario.id)
    return UsuarioConClave(usuario=_usuario_admin(usuario, saldo), clave_temporal=clave)


@router.post("/{usuario_id}/bloquear", response_model=UsuarioAdmin)
async def bloquear(usuario_id: int, request: Request, actual: Admin, bd: Bd):
    """Bloquea y cierra todas sus sesiones (RF-03, RF-04, RF-06)."""
    if usuario_id == actual.usuario_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, MENSAJE_BLOQUEARSE)
    usuario, saldo = await _bloquear_usuario(bd, usuario_id)
    usuario.activo = False
    await sesiones.cerrar_sesiones_de(bd, usuario.id)
    auditoria.registrar(
        bd,
        actual.usuario_id,
        "bloquear_usuario",
        {"usuario_id": usuario.id, "usuario": usuario.usuario},
        ip_cliente(request),
    )
    await bd.commit()
    return _usuario_admin(usuario, saldo)


@router.post("/{usuario_id}/desbloquear", response_model=UsuarioAdmin)
async def desbloquear(usuario_id: int, request: Request, actual: Admin, bd: Bd):
    usuario, saldo = await _bloquear_usuario(bd, usuario_id)
    usuario.activo = True
    auditoria.registrar(
        bd,
        actual.usuario_id,
        "desbloquear_usuario",
        {"usuario_id": usuario.id, "usuario": usuario.usuario},
        ip_cliente(request),
    )
    await bd.commit()
    return _usuario_admin(usuario, saldo)


@router.post("/{usuario_id}/reset-clave", response_model=UsuarioConClave)
async def resetear_clave(usuario_id: int, request: Request, actual: Admin, bd: Bd):
    """Nueva clave temporal: debe cambiarla y se cierran sus sesiones (RF-02, RF-03, RF-06)."""
    usuario, saldo = await _bloquear_usuario(bd, usuario_id)
    clave = auth_service.generar_clave_temporal()
    usuario.hash_password = auth_service.hashear_clave(clave)
    usuario.debe_cambiar_clave = True
    await sesiones.cerrar_sesiones_de(bd, usuario.id)
    auditoria.registrar(
        bd,
        actual.usuario_id,
        "resetear_clave",
        {"usuario_id": usuario.id, "usuario": usuario.usuario},
        ip_cliente(request),
    )
    await bd.commit()
    return UsuarioConClave(usuario=_usuario_admin(usuario, saldo), clave_temporal=clave)


def _movimiento_usuario(
    movimiento: Movimiento, pedido_codigo: str | None, registrado_por: str | None
) -> MovimientoUsuario:
    monto = movimiento.monto
    if movimiento.tipo in TIPOS_QUE_RESTAN:
        monto = -monto
    return MovimientoUsuario(
        id=movimiento.id,
        fecha=movimiento.fecha,
        tipo=movimiento.tipo,
        monto=monto,
        saldo_disponible_resultante=movimiento.saldo_disponible_resultante,
        saldo_reservado_resultante=movimiento.saldo_reservado_resultante,
        nota=movimiento.nota,
        pedido_id=movimiento.pedido_id,
        pedido_codigo=pedido_codigo,
        registrado_por=registrado_por or REGISTRADO_POR_SISTEMA,
    )


@router.get("/{usuario_id}/movimientos", response_model=ListaMovimientos)
async def movimientos(
    usuario_id: int,
    bd: Bd,
    tipo: Literal["abono", "ajuste", "reserva", "liberacion", "cargo"] | None = None,
    desde: datetime | None = None,
    hasta: datetime | None = None,
    pagina: Annotated[int, Query(ge=1)] = 1,
    por_pagina: Annotated[int, Query(ge=1, le=POR_PAGINA_MAXIMO)] = POR_PAGINA,
):
    """Historial de movimientos de saldo del cliente, del más reciente al más antiguo (RF-43).

    `desde` es inclusivo y `hasta` exclusivo. Solo lectura: no modifica el libro (RF-42).
    """
    if await bd.scalar(select(Usuario.id).where(Usuario.id == usuario_id)) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, MENSAJE_NO_ENCONTRADO)
    registrador = aliased(Usuario)
    consulta = (
        select(Movimiento, Pedido.codigo, registrador.usuario)
        .outerjoin(Pedido, Pedido.id == Movimiento.pedido_id)
        .outerjoin(registrador, registrador.id == Movimiento.creado_por)
        .where(Movimiento.usuario_id == usuario_id)
    )
    if tipo is not None:
        consulta = consulta.where(Movimiento.tipo == tipo)
    if desde is not None:
        consulta = consulta.where(Movimiento.fecha >= utc(desde))
    if hasta is not None:
        consulta = consulta.where(Movimiento.fecha < utc(hasta))
    total = await bd.scalar(select(func.count()).select_from(consulta.subquery()))
    filas = await bd.execute(
        consulta.order_by(Movimiento.fecha.desc(), Movimiento.id.desc())
        .limit(por_pagina)
        .offset((pagina - 1) * por_pagina)
    )
    return ListaMovimientos(
        movimientos=[_movimiento_usuario(*fila) for fila in filas],
        total=total or 0,
        pagina=pagina,
        por_pagina=por_pagina,
    )
