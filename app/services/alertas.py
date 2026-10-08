"""Alertas visibles para el admin (RN-08, RN-11, plan sec. 4.2.1).

Una sola alerta activa (no atendida) por tipo: el alta usa
`INSERT … ON CONFLICT DO NOTHING` sobre el índice parcial `uq_alertas_tipo_activa`.
No hace commit: corre dentro de la transacción de quien la llama.
"""

import logging
from decimal import Decimal, InvalidOperation

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Alerta, Auditoria, Config
from app.models.alertas import TIPOS_ALERTA

logger = logging.getLogger(__name__)

CLAVE_UMBRAL = "alerta_credito_min"
UMBRAL_POR_DEFECTO = Decimal("10.00")


class AlertaInexistente(LookupError):
    """No existe una alerta con el id indicado."""


async def umbral_credito(sesion: AsyncSession) -> Decimal:
    """Umbral de crédito bajo (RN-11), con valor por defecto si falta o es inválido."""
    valor = await sesion.scalar(select(Config.valor).where(Config.clave == CLAVE_UMBRAL))
    if valor is None:
        logger.warning("Falta la configuración %s; se usa %s", CLAVE_UMBRAL, UMBRAL_POR_DEFECTO)
        return UMBRAL_POR_DEFECTO
    try:
        umbral = Decimal(valor)
    except InvalidOperation:
        umbral = None
    if umbral is None or not umbral.is_finite() or umbral < 0:
        logger.warning("Valor inválido en %s; se usa %s", CLAVE_UMBRAL, UMBRAL_POR_DEFECTO)
        return UMBRAL_POR_DEFECTO
    return umbral


async def registrar_alerta(sesion: AsyncSession, tipo: str, mensaje: str) -> bool:
    """Crea una alerta activa del tipo indicado.

    Devuelve True si se insertó, False si ya existía una activa de ese tipo.
    """
    if tipo not in TIPOS_ALERTA:
        raise ValueError(f"Tipo de alerta desconocido: {tipo!r}")
    insertar = (
        insert(Alerta)
        .values(tipo=tipo, mensaje=mensaje)
        .on_conflict_do_nothing(
            index_elements=["tipo"],
            index_where=Alerta.atendida_en.is_(None),
        )
        .returning(Alerta.id)
    )
    creada = (await sesion.execute(insertar)).scalar()
    if creada is not None:
        logger.warning("Alerta creada (%s): %s", tipo, mensaje)
        return True
    return False


async def comprobar_credito(sesion: AsyncSession, credito: Decimal) -> bool:
    """Registra `credito_bajo` si el crédito queda por debajo del umbral (RN-11 a)."""
    umbral = await umbral_credito(sesion)
    if credito < umbral:
        mensaje = f"Crédito en VentasFF bajo: {credito:.2f} USD (umbral {umbral:.2f} USD)"
        return await registrar_alerta(sesion, "credito_bajo", mensaje)
    return False


async def alertas_activas(sesion: AsyncSession) -> list[Alerta]:
    """Alertas no atendidas, las más recientes primero."""
    consulta = (
        select(Alerta)
        .where(Alerta.atendida_en.is_(None))
        .order_by(Alerta.creada_en.desc(), Alerta.id.desc())
    )
    return list((await sesion.scalars(consulta)).all())


async def atender_alerta(
    sesion: AsyncSession, alerta_id: int, *, admin_id: int, ip: str | None = None
) -> Alerta:
    """Marca una alerta como atendida y lo deja en auditoría.

    Idempotente: si ya estaba atendida se devuelve sin cambios ni auditoría nueva.
    """
    consulta = (
        select(Alerta)
        .where(Alerta.id == alerta_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    alerta = await sesion.scalar(consulta)
    if alerta is None:
        raise AlertaInexistente(f"No existe la alerta {alerta_id}")
    if alerta.atendida_en is not None:
        return alerta
    alerta.atendida_en = func.now()
    alerta.atendida_por = admin_id
    sesion.add(
        Auditoria(
            usuario_id=admin_id,
            accion="atender_alerta",
            detalle={"alerta": alerta.id, "tipo": alerta.tipo},
            ip=ip,
        )
    )
    await sesion.flush()
    await sesion.refresh(alerta)
    return alerta
