"""Comandos de administración.

    python -m app.cli crear-admin <usuario>

Crea el primer admin con clave temporal; debe cambiarla al primer ingreso (RF-02).
La clave se muestra una sola vez por la salida estándar y nunca se registra en logs.
"""

import argparse
import asyncio
import sys

from sqlalchemy import exists, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import ErrorConfiguracion, obtener_configuracion
from app.db import ErrorConexionBD, crear_fabrica_sesiones, crear_motor, verificar_conexion
from app.models import Usuario
from app.services import auth_service
from app.services.auth_service import ErrorUsuario


class AdminExistente(Exception):
    pass


async def crear_primer_admin(sesion: AsyncSession, nombre: str) -> tuple[Usuario, str]:
    """Crea el admin solo si aún no hay ninguno. No hace commit."""
    if await sesion.scalar(select(exists().where(Usuario.rol == "admin"))):
        raise AdminExistente("Ya existe un admin; los demás usuarios se crean desde el panel")
    return await auth_service.crear_usuario(sesion, nombre, rol="admin")


async def crear_admin(fabrica: async_sessionmaker, nombre: str) -> int:
    async with fabrica() as sesion:
        try:
            usuario, clave = await crear_primer_admin(sesion, nombre)
            await sesion.commit()
        except (AdminExistente, ErrorUsuario) as error:
            print(f"Error: {error}", file=sys.stderr)
            return 1
    print(f"Admin {usuario.usuario!r} creado.")
    print(f"Clave temporal (se muestra una sola vez): {clave}")
    print("Deberá cambiarla al iniciar sesión.")
    return 0


async def _crear_admin_desde_entorno(nombre: str) -> int:
    motor = crear_motor(obtener_configuracion().database_url.get_secret_value())
    try:
        await verificar_conexion(motor)
        return await crear_admin(crear_fabrica_sesiones(motor), nombre)
    finally:
        await motor.dispose()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.cli")
    comandos = parser.add_subparsers(dest="comando", required=True)
    crear = comandos.add_parser("crear-admin", help="Crea el primer admin con clave temporal")
    crear.add_argument("usuario")
    args = parser.parse_args(argv)

    try:
        return asyncio.run(_crear_admin_desde_entorno(args.usuario))
    except (ErrorConfiguracion, ErrorConexionBD) as error:
        print(error, file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
