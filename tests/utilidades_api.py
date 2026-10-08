"""Ayudas para las pruebas de la API: usuarios con clave conocida y login."""

import uuid

import httpx

from app.models import Usuario
from app.services import auth_service, ledger

CLAVE = "clave-de-prueba-1"


async def crear_usuario_con_clave(
    sesion,
    rol: str = "cliente",
    *,
    clave: str = CLAVE,
    debe_cambiar_clave: bool = False,
    activo: bool = True,
) -> Usuario:
    """Usuario confirmado en la BD; los clientes reciben su cuenta de saldo en cero."""
    usuario = Usuario(
        usuario=f"u_{uuid.uuid4().hex[:12]}",
        hash_password=auth_service.hashear_clave(clave),
        rol=rol,
        debe_cambiar_clave=debe_cambiar_clave,
        activo=activo,
    )
    sesion.add(usuario)
    await sesion.flush()
    if rol == "cliente":
        await ledger.abrir_cuenta(sesion, usuario.id)
    await sesion.commit()
    return usuario


async def iniciar_sesion(
    cliente: httpx.AsyncClient, usuario: str, clave: str = CLAVE
) -> httpx.Response:
    """Inicia sesión y deja el token CSRF como cabecera por defecto del cliente."""
    respuesta = await cliente.post("/auth/login", json={"usuario": usuario, "clave": clave})
    if respuesta.status_code == 200:
        cliente.headers["X-CSRF-Token"] = respuesta.json()["csrf"]
    return respuesta
