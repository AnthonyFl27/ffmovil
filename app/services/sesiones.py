"""Sesiones guardadas en la BD (RF-06, plan sec. 7).

La cookie lleva un token aleatorio; en `sesiones` solo se guarda su SHA-256.
Cada sesión tiene su token CSRF. Ninguna función hace commit.
"""

import hashlib
import secrets
from dataclasses import dataclass
from datetime import timedelta

from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Sesion, Usuario

# RF-06: la sesión expira tras 8 h sin actividad.
EXPIRACION = timedelta(hours=8)
# `ultima_actividad` se actualiza como mucho una vez por minuto.
INTERVALO_REFRESCO = timedelta(minutes=1)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


@dataclass(frozen=True)
class SesionCreada:
    token: str
    csrf: str


@dataclass(frozen=True)
class SesionValida:
    registro: Sesion
    usuario: Usuario


async def crear_sesion(sesion: AsyncSession, usuario_id: int, ip: str | None) -> SesionCreada:
    token = secrets.token_urlsafe(32)
    csrf = secrets.token_urlsafe(32)
    sesion.add(Sesion(token_hash=hash_token(token), usuario_id=usuario_id, csrf=csrf, ip=ip))
    await sesion.flush()
    return SesionCreada(token, csrf)


async def obtener_sesion(sesion: AsyncSession, token: str) -> SesionValida | None:
    """Sesión vigente del token con su usuario, o None.

    Si la sesión venció o el usuario está bloqueado (RF-04), borra la fila y
    devuelve None. Renueva `ultima_actividad` si pasó el intervalo de refresco.
    """
    token_hash = hash_token(token)
    fila = (
        await sesion.execute(
            select(Sesion, Usuario, func.now())
            .join(Usuario, Usuario.id == Sesion.usuario_id)
            .where(Sesion.token_hash == token_hash)
        )
    ).first()
    if fila is None:
        return None
    registro, usuario, ahora = fila
    inactiva = ahora - registro.ultima_actividad
    if inactiva >= EXPIRACION or not usuario.activo:
        await cerrar_sesion(sesion, token_hash)
        return None
    if inactiva >= INTERVALO_REFRESCO:
        await sesion.execute(
            update(Sesion)
            .where(Sesion.token_hash == token_hash)
            .values(ultima_actividad=func.now())
        )
    return SesionValida(registro, usuario)


async def cerrar_sesion(sesion: AsyncSession, token_hash: str) -> None:
    await sesion.execute(delete(Sesion).where(Sesion.token_hash == token_hash))


async def cerrar_sesiones_de(
    sesion: AsyncSession, usuario_id: int, *, excepto: str | None = None
) -> None:
    """Cierra todas las sesiones del usuario, salvo la de hash `excepto` (RF-06)."""
    consulta = delete(Sesion).where(Sesion.usuario_id == usuario_id)
    if excepto is not None:
        consulta = consulta.where(Sesion.token_hash != excepto)
    await sesion.execute(consulta)


async def limpiar_vencidas(sesion: AsyncSession) -> None:
    await sesion.execute(delete(Sesion).where(Sesion.ultima_actividad < func.now() - EXPIRACION))
