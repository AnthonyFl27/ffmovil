"""Contraseñas con argon2 y alta de usuarios con clave temporal (RF-01, RF-02, RNF-03).

Las contraseñas nunca se registran en logs (RNF-05); la clave temporal solo se
devuelve a quien crea el usuario para que se la entregue.
"""

import re
import secrets

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from sqlalchemy import func, select
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


class ClaveInvalida(ErrorUsuario):
    """La contraseña nueva no cumple la política (RF-08)."""


class UsuarioBloqueado(ErrorUsuario):
    """Credenciales correctas, pero la cuenta está bloqueada (RF-04)."""


# RF-07: de 3 a 30 caracteres: a-z, dígitos, '.', '_' y '-'; se guarda en minúsculas.
PATRON_USUARIO = re.compile(r"[a-z0-9._-]{3,30}")
# RF-08
LARGO_MINIMO_CLAVE = 8
LARGO_MAXIMO_CLAVE = 128


def normalizar_nombre_usuario(nombre: str) -> str:
    """Nombre en minúsculas y sin espacios alrededor, o `DatosUsuarioInvalidos` (RF-07)."""
    nombre = nombre.strip().lower() if isinstance(nombre, str) else ""
    if not PATRON_USUARIO.fullmatch(nombre):
        raise DatosUsuarioInvalidos(
            "El usuario debe tener de 3 a 30 caracteres: letras minúsculas, números, '.', '_' o '-'"
        )
    return nombre


def validar_clave_nueva(clave: str, hash_actual: str) -> str:
    """Política mínima de contraseñas (RF-08): de 8 a 128 caracteres y distinta de la actual."""
    if not isinstance(clave, str) or not (LARGO_MINIMO_CLAVE <= len(clave) <= LARGO_MAXIMO_CLAVE):
        raise ClaveInvalida(
            f"La contraseña debe tener de {LARGO_MINIMO_CLAVE} a {LARGO_MAXIMO_CLAVE} caracteres"
        )
    if verificar_clave(hash_actual, clave):
        raise ClaveInvalida("La contraseña nueva debe ser distinta de la actual")
    return clave


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


# Hash de referencia: si el usuario no existe se verifica igual, para que el tiempo
# de respuesta no revele qué usuarios existen.
_HASH_FICTICIO = _hasher.hash(secrets.token_urlsafe(16))


async def autenticar(sesion: AsyncSession, nombre: str, clave: str) -> Usuario | None:
    """Usuario si las credenciales son correctas (RF-01); None si no.

    Si son correctas pero la cuenta está bloqueada lanza `UsuarioBloqueado` (RF-04).
    Rehashea la clave si los parámetros de argon2 cambiaron. No hace commit.
    """
    nombre = nombre.strip().lower() if isinstance(nombre, str) else ""
    usuario = None
    if nombre:
        usuario = await sesion.scalar(select(Usuario).where(func.lower(Usuario.usuario) == nombre))
    if usuario is None:
        verificar_clave(_HASH_FICTICIO, clave or "")
        return None
    if not verificar_clave(usuario.hash_password, clave or ""):
        return None
    if not usuario.activo:
        raise UsuarioBloqueado("Cuenta bloqueada. Contacta al administrador.")
    if requiere_rehash(usuario.hash_password):
        usuario.hash_password = hashear_clave(clave)
    return usuario


async def crear_usuario(
    sesion: AsyncSession, nombre: str, rol: str = "cliente"
) -> tuple[Usuario, str]:
    """Crea el usuario con clave temporal y `debe_cambiar_clave` (RF-02).

    Los clientes reciben además su cuenta de saldo en cero. Devuelve el usuario y
    la clave temporal en claro. No hace commit.
    """
    nombre = normalizar_nombre_usuario(nombre)
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
