"""Recuperación de pedidos huérfanos tras un reinicio (RN-09, plan sec. 4.3).

Un pedido en `PROCESANDO` que sobrevive a un reinicio no sabe si VentasFF llegó
a recargarlo. Pasa a `PENDIENTE_VERIFICAR`: el saldo queda retenido (sin
movimientos en el ledger) y nunca se reintenta automáticamente (RN-04).
"""

import logging
from datetime import timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Pedido
from app.services.estados import Estado
from app.services.recarga_service import cambiar_estado

logger = logging.getLogger(__name__)

DETALLE_RECUPERACION = "Servicio reiniciado durante la recarga: verificar en VentasFF"


async def recuperar_pedidos_huerfanos(
    sesion: AsyncSession, *, antiguedad_minima: timedelta = timedelta(0)
) -> list[str]:
    """Pasa a `PENDIENTE_VERIFICAR` los pedidos en `PROCESANDO` más antiguos que el umbral.

    Se llama al arrancar la aplicación. La app corre con un único worker, así que
    cualquier pedido `PROCESANDO` en el arranque es huérfano; por eso el umbral
    por defecto es 0. No toca el ledger: el saldo sigue reservado.

    Confirma una sola vez y devuelve los códigos de los pedidos recuperados.
    """
    consulta = (
        select(Pedido)
        .where(
            Pedido.estado == Estado.PROCESANDO,
            Pedido.actualizado_en <= func.now() - antiguedad_minima,
        )
        .order_by(Pedido.id)
        .with_for_update(skip_locked=True)
        .execution_options(populate_existing=True)
    )
    pedidos = (await sesion.scalars(consulta)).all()

    codigos: list[str] = []
    for pedido in pedidos:
        await cambiar_estado(
            sesion, pedido, Estado.PENDIENTE_VERIFICAR, detalle=DETALLE_RECUPERACION
        )
        codigos.append(pedido.codigo)

    await sesion.commit()

    if codigos:
        logger.warning(
            "Pedidos recuperados tras reinicio a PENDIENTE_VERIFICAR: %d %s",
            len(codigos),
            ", ".join(str(codigo) for codigo in codigos),
        )
    return codigos
