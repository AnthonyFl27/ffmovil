"""Consulta del registro de acciones del admin (RF-55)."""

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Query
from sqlalchemy import func, select

from app.models import Auditoria, Usuario
from app.routers.dependencias import Bd
from app.schemas.admin import ListaAuditoria, RegistroAuditoria
from app.services.consultas_pedidos import POR_PAGINA, POR_PAGINA_MAXIMO, utc

router = APIRouter()


@router.get("/auditoria", response_model=ListaAuditoria)
async def listar(
    bd: Bd,
    accion: str | None = None,
    usuario_id: int | None = None,
    desde: datetime | None = None,
    hasta: datetime | None = None,
    pagina: Annotated[int, Query(ge=1)] = 1,
    por_pagina: Annotated[int, Query(ge=1, le=POR_PAGINA_MAXIMO)] = POR_PAGINA,
):
    """Acciones del admin, las más recientes primero; `desde` inclusivo, `hasta` exclusivo."""
    consulta = select(Auditoria, Usuario.usuario).outerjoin(
        Usuario, Usuario.id == Auditoria.usuario_id
    )
    if accion:
        consulta = consulta.where(Auditoria.accion == accion)
    if usuario_id is not None:
        consulta = consulta.where(Auditoria.usuario_id == usuario_id)
    if desde is not None:
        consulta = consulta.where(Auditoria.fecha >= utc(desde))
    if hasta is not None:
        consulta = consulta.where(Auditoria.fecha < utc(hasta))
    total = await bd.scalar(select(func.count()).select_from(consulta.subquery()))
    filas = await bd.execute(
        consulta.order_by(Auditoria.fecha.desc(), Auditoria.id.desc())
        .limit(por_pagina)
        .offset((pagina - 1) * por_pagina)
    )
    return ListaAuditoria(
        registros=[
            RegistroAuditoria(
                id=registro.id,
                fecha=registro.fecha,
                usuario_id=registro.usuario_id,
                usuario=usuario,
                accion=registro.accion,
                detalle=registro.detalle,
                ip=str(registro.ip) if registro.ip is not None else None,
            )
            for registro, usuario in filas
        ],
        total=total or 0,
        pagina=pagina,
        por_pagina=por_pagina,
    )
