"""Ayudas compartidas por las pruebas de base de datos."""

import uuid

from app.models import Usuario


def nuevo_usuario(rol: str = "cliente") -> Usuario:
    return Usuario(usuario=f"u_{uuid.uuid4().hex[:12]}", hash_password="x", rol=rol)


async def crear_usuario(sesion, rol: str = "cliente") -> Usuario:
    usuario = nuevo_usuario(rol)
    sesion.add(usuario)
    await sesion.flush()
    return usuario
