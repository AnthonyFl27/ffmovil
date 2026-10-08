"""Dependencias comunes de las rutas: BD, sesión, CSRF y roles (plan sec. 7).

- `usuario_en_sesion`: cualquier sesión válida (solo para logout, sesión y cambio de clave).
- `usuario_actual`: además rechaza a quien debe cambiar la contraseña (RF-02).
- `require_admin`: además exige rol admin (RNF-03).
"""

import hmac
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Usuario
from app.services import sesiones

COOKIE_SESION = "sesion"
CABECERA_CSRF = "X-CSRF-Token"
METODOS_SEGUROS = frozenset({"GET", "HEAD", "OPTIONS"})

MENSAJE_SIN_SESION = "Sesión no válida o vencida. Inicia sesión de nuevo."
MENSAJE_CSRF = "Token CSRF ausente o inválido."
MENSAJE_CAMBIAR_CLAVE = "Debes cambiar tu contraseña antes de continuar."
MENSAJE_SOLO_ADMIN = "Acceso solo para administradores."


async def obtener_bd(request: Request) -> AsyncIterator[AsyncSession]:
    async with request.app.state.sesiones() as sesion:
        yield sesion


Bd = Annotated[AsyncSession, Depends(obtener_bd)]


def ip_cliente(request: Request) -> str | None:
    return request.client.host if request.client else None


@dataclass(frozen=True)
class SesionActual:
    usuario: Usuario
    token_hash: str
    csrf: str

    @property
    def usuario_id(self) -> int:
        return self.usuario.id


async def usuario_en_sesion(request: Request, bd: Bd) -> SesionActual:
    token = request.cookies.get(COOKIE_SESION)
    valida = await sesiones.obtener_sesion(bd, token) if token else None
    # Guarda el refresco de actividad o el borrado de una sesión vencida.
    await bd.commit()
    if valida is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, MENSAJE_SIN_SESION)
    if request.method not in METODOS_SEGUROS:
        enviado = request.headers.get(CABECERA_CSRF, "")
        if not hmac.compare_digest(enviado.encode(), valida.registro.csrf.encode()):
            raise HTTPException(status.HTTP_403_FORBIDDEN, MENSAJE_CSRF)
    return SesionActual(valida.usuario, valida.registro.token_hash, valida.registro.csrf)


EnSesion = Annotated[SesionActual, Depends(usuario_en_sesion)]


async def usuario_actual(actual: EnSesion) -> SesionActual:
    if actual.usuario.debe_cambiar_clave:
        raise HTTPException(status.HTTP_403_FORBIDDEN, MENSAJE_CAMBIAR_CLAVE)
    return actual


# Cualquier usuario con sesión y contraseña ya cambiada (cliente o admin).
Actual = Annotated[SesionActual, Depends(usuario_actual)]


async def require_admin(actual: Actual) -> SesionActual:
    if actual.usuario.rol != "admin":
        raise HTTPException(status.HTTP_403_FORBIDDEN, MENSAJE_SOLO_ADMIN)
    return actual


Admin = Annotated[SesionActual, Depends(require_admin)]
