"""Tareas programadas: sincronización diaria del catálogo (RF-10, plan sec. 5).

La sincronización corre con APScheduler dentro del proceso de la app. Debe
ejecutarse en un único worker de uvicorn para no duplicar sincronizaciones: el
Dockerfile arranca uvicorn con `--workers 1`.
"""

import json
import logging
from collections.abc import Callable
from datetime import UTC, datetime

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models import Config
from app.services.catalogo import ResumenSincronizacion, sincronizar_catalogo
from app.services.ventasff_client import ClienteVentasFF, ErrorVentasFF

logger = logging.getLogger(__name__)

CLAVE_ULTIMA_SINCRONIZACION = "catalogo_ultima_sincronizacion"
ID_TAREA_SINCRONIZACION = "sincronizar_catalogo"


def _ahora() -> str:
    return datetime.now(UTC).isoformat()


async def _registrar_resultado(sesion: AsyncSession, datos: dict) -> None:
    await sesion.merge(Config(clave=CLAVE_ULTIMA_SINCRONIZACION, valor=json.dumps(datos)))


async def ejecutar_sincronizacion(
    fabrica: async_sessionmaker,
    crear_cliente: Callable[[], ClienteVentasFF],
) -> ResumenSincronizacion | None:
    """Sincroniza el catálogo y guarda el resultado en `config`.

    Los cambios del catálogo y el registro de resultado se confirman en un solo
    commit. Si VentasFF falla, no propaga `ErrorVentasFF` (es un trabajo
    programado): registra el error y devuelve None.
    """
    async with fabrica() as sesion:
        try:
            async with crear_cliente() as cliente:
                resumen = await sincronizar_catalogo(sesion, cliente)
        except ErrorVentasFF as error:
            await sesion.rollback()
            # Solo el nombre de la clase y su mensaje: nunca cabeceras ni claves.
            logger.error("Sincronización del catálogo fallida: %s: %s", type(error).__name__, error)
            await _registrar_resultado(
                sesion,
                {
                    "fecha": _ahora(),
                    "resultado": "error",
                    "detalle": f"{type(error).__name__}: {error}",
                },
            )
            await sesion.commit()
            return None

        await _registrar_resultado(
            sesion,
            {
                "fecha": _ahora(),
                "resultado": "ok",
                "recibidos": resumen.recibidos,
                "nuevos": resumen.nuevos,
                "actualizados": resumen.actualizados,
                "desactivados": resumen.desactivados,
                "bajo_costo": resumen.bajo_costo,
            },
        )
        await sesion.commit()
    logger.info("Sincronización del catálogo correcta: %s", resumen)
    return resumen


def crear_programador(
    fabrica: async_sessionmaker,
    crear_cliente: Callable[[], ClienteVentasFF],
    *,
    hora_utc: int = 8,
) -> AsyncIOScheduler:
    """Programador (sin arrancar) con la sincronización diaria a `hora_utc`.

    Debe usarse en un único worker de la app: con varios procesos se duplicaría
    la sincronización (plan sec. 5). El Dockerfile usa `--workers 1`.
    """
    programador = AsyncIOScheduler(timezone="UTC")
    programador.add_job(
        ejecutar_sincronizacion,
        trigger=CronTrigger(hour=hora_utc, minute=0, timezone="UTC"),
        args=[fabrica, crear_cliente],
        id=ID_TAREA_SINCRONIZACION,
        max_instances=1,
        coalesce=True,
        misfire_grace_time=3600,
        replace_existing=True,
    )
    return programador
