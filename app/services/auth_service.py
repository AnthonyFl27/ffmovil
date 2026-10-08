"""Contraseñas con argon2 y alta de usuarios con clave temporal (RF-01, RF-02, RNF-03).

Las contraseñas nunca se registran en logs (RNF-05); la clave temporal solo se
devuelve a quien crea el usuario para que se la entregue.
"""

import secrets

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Usuario
from app.models.usuarios import ROLES
from app.services import ledger

_hasher = PasswordHasher()


class ErrorUsuario(Exception):
    pass


class UsuarioDuplicado(ErrorUsuario):
    pass


class DatosUsuarioInvalidos(ErrorUsuario):
    pass


def hashear_clave(clave: str) -> str:
    return _hasher.hash(clave)


def verificar_clave(hash_password: str, clave: str) -> bool:
    try:
        return _hasher.verify(hash_password, clave)
    except (VerificationError, InvalidHashError):
        return False


def requiere_rehash(hash_password: str) -> bool:
    """True si el hash usa parámetros anteriores a los actuales."""
    return _hasher.check_needs_rehash(hash_password)


def generar_clave_temporal() -> str:
    return secrets.token_urlsafe(12)


async def crear_usuario(
    sesion: AsyncSession, nombre: str, rol: str = "cliente"
) -> tuple[Usuario, str]:
    """Crea el usuario con clave temporal y `debe_cambiar_clave` (RF-02).

    Los clientes reciben además su cuenta de saldo en cero. Devuelve el usuario y
    la clave temporal en claro. No hace commit.
    """
    nombre = nombre.strip() if nombre else ""
    if not nombre:
        raise DatosUsuarioInvalidos("El nombre de usuario es obligatorio")
    if rol not in ROLES:
        raise DatosUsuarioInvalidos(f"Rol inválido: {rol!r}")

    clave = generar_clave_temporal()
    usuario = Usuario(
        usuario=nombre, hash_password=hashear_clave(clave), rol=rol, debe_cambiar_clave=True
    )
    try:
        # Savepoint: un duplicado no invalida la transacción de quien llama.
        async with sesion.begin_nested():
            sesion.add(usuario)
            await sesion.flush()
    except IntegrityError as error:
        if "uq_usuarios_usuario" in str(error.orig):
            raise UsuarioDuplicado(f"El usuario {nombre!r} ya existe") from None
        raise
    if rol == "cliente":
        await ledger.abrir_cuenta(sesion, usuario.id)
    return usuario, clave
