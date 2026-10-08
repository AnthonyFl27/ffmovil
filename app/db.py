"""Conexión a la base de datos externa por `DATABASE_URL` (RNF-07)."""

from sqlalchemy import make_url, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine


class ErrorConexionBD(RuntimeError):
    """No se pudo conectar a la base de datos."""


def crear_motor(url: str, esquema: str | None = None) -> AsyncEngine:
    """`esquema` fija el search_path de cada conexión (las pruebas usan `test`, RNF-10)."""
    connect_args = {"options": f"-csearch_path={esquema}"} if esquema else {}
    return create_async_engine(url, pool_pre_ping=True, connect_args=connect_args)


def crear_fabrica_sesiones(motor: AsyncEngine) -> async_sessionmaker:
    return async_sessionmaker(motor, expire_on_commit=False)


async def verificar_conexion(motor: AsyncEngine) -> None:
    """Falla con un error claro si la base no responde. Nunca incluye la contraseña."""
    try:
        async with motor.connect() as conexion:
            await conexion.execute(text("SELECT 1"))
    except (SQLAlchemyError, OSError) as error:
        original = getattr(error, "orig", None) or error
        detalle = str(original).strip().splitlines()[0] if str(original).strip() else ""
        clave = make_url(motor.url).password
        if clave:
            detalle = detalle.replace(clave, "***")
        url_segura = motor.url.render_as_string(hide_password=True)
        raise ErrorConexionBD(
            f"No se pudo conectar a la base de datos ({url_segura}): "
            f"{type(original).__name__}: {detalle}. "
            "Revisa DATABASE_URL y que el servidor sea accesible."
        ) from None
