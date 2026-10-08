"""Filtros y paginación de listados de pedidos (RF-32, RF-50, CA-06).

Solo arma consultas; no hace commit ni modifica datos.
"""

from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import Select, false, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Pedido
from app.services.codigos import id_desde_codigo
from app.services.estados import Estado

POR_PAGINA = 20
POR_PAGINA_MAXIMO = 100


def _utc(fecha: datetime) -> datetime:
    """Una fecha sin zona se toma como UTC (RNF-09)."""
    return fecha if fecha.tzinfo is not None else fecha.replace(tzinfo=UTC)


@dataclass(frozen=True)
class FiltrosPedido:
    """Filtros comunes; `desde` es inclusivo y `hasta` exclusivo."""

    estado: Estado | None = None
    desde: datetime | None = None
    hasta: datetime | None = None
    player_id: str | None = None
    codigo: str | None = None

    def aplicar(self, consulta: Select) -> Select:
        if self.estado is not None:
            # "Procesando" agrupa CREADO y PROCESANDO (spec sec. 7).
            if self.estado in (Estado.CREADO, Estado.PROCESANDO):
                consulta = consulta.where(Pedido.estado.in_((Estado.CREADO, Estado.PROCESANDO)))
            else:
                consulta = consulta.where(Pedido.estado == self.estado)
        if self.desde is not None:
            consulta = consulta.where(Pedido.creado_en >= _utc(self.desde))
        if self.hasta is not None:
            consulta = consulta.where(Pedido.creado_en < _utc(self.hasta))
        if self.player_id:
            consulta = consulta.where(Pedido.player_id == self.player_id.strip())
        if self.codigo:
            pedido_id = id_desde_codigo(self.codigo)
            consulta = consulta.where(Pedido.id == pedido_id if pedido_id else false())
        return consulta


@dataclass(frozen=True)
class Pagina:
    filas: list
    total: int
    pagina: int
    por_pagina: int


async def paginar(sesion: AsyncSession, consulta: Select, pagina: int, por_pagina: int) -> Pagina:
    """Ejecuta `consulta` (ya filtrada) ordenada de más reciente a más antigua."""
    total = await sesion.scalar(
        select(func.count()).select_from(consulta.order_by(None).subquery())
    )
    filas = (
        await sesion.execute(
            consulta.order_by(Pedido.creado_en.desc(), Pedido.id.desc())
            .limit(por_pagina)
            .offset((pagina - 1) * por_pagina)
        )
    ).all()
    return Pagina(list(filas), total or 0, pagina, por_pagina)
