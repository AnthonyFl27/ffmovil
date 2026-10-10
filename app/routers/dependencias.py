"""Dependencias comunes de las rutas: BD, sesión, CSRF y roles (plan sec. 7).

- `usuario_en_sesion`: cualquier sesión válida (solo para logout, sesión y cambio de clave).
- `usuario_actual`: además rechaza a quien debe cambiar la contraseña (RF-02).
- `require_admin`: además exige rol admin (RNF-03).
"""

import hmac
import ipaddress
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
MENSAJE_SOLO_CLIENTE = "Acceso solo para clientes."


async def obtener_bd(request: Request) -> AsyncIterator[AsyncSession]:
    async with request.app.state.sesiones() as sesion:
        yield sesion


Bd = Annotated[AsyncSession, Depends(obtener_bd)]


# Redes de un proxy local o de Docker. Explícitas: `is_private` de Python también incluye
# rangos de documentación y otros especiales que no son una red interna.
REDES_DE_CONFIANZA = tuple(
    ipaddress.ip_network(red)
    for red in (
        "127.0.0.0/8",
        "::1/128",
        "10.0.0.0/8",
        "172.16.0.0/12",
        "192.168.0.0/16",
        "fc00::/7",
    )
)


def _es_proxy_de_confianza(host: str) -> bool:
    """Loopback o red privada (proxy local o red de Docker); nunca una IP pública."""
    try:
        direccion = ipaddress.ip_address(host)
    except ValueError:
        return False
    return any(direccion in red for red in REDES_DE_CONFIANZA if red.version == direccion.version)


def ip_cliente(request: Request) -> str | None:
    """IP del cliente (RNF-16): la de la conexión o, tras un proxy de confianza, la de la cabecera."""
    host = request.client.host if request.client else None
    cabecera = getattr(request.app.state, "cabecera_ip", "")
    if cabecera and host and _es_proxy_de_confianza(host):
        valor = request.headers.get(cabecera, "")
        # El último valor es el que añadió nuestro proxy; los anteriores los pone el cliente.
        candidata = valor.split(",")[-1].strip()
        try:
            return str(ipaddress.ip_address(candidata))
        except ValueError:
            pass
    return host


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


async def require_cliente(actual: Actual) -> SesionActual:
    """Rutas del cliente (`/me`, `/recargas`): los admins no tienen cuenta de saldo."""
    if actual.usuario.rol != "cliente":
        raise HTTPException(status.HTTP_403_FORBIDDEN, MENSAJE_SOLO_CLIENTE)
    return actual


Cliente = Annotated[SesionActual, Depends(require_cliente)]
