"""T-015: argon2 y alta de usuarios con clave temporal (RF-01, RF-02, RNF-03)."""

import uuid
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.models import Saldo, Usuario
from app.services import auth_service
from app.services.auth_service import DatosUsuarioInvalidos, UsuarioDuplicado


def nombre_unico() -> str:
    return f"cli_{uuid.uuid4().hex[:10]}"


def test_hash_argon2id_verificable():
    hash_ = auth_service.hashear_clave("secreta-123")
    assert hash_.startswith("$argon2id$")
    assert "secreta-123" not in hash_
    assert auth_service.verificar_clave(hash_, "secreta-123")
    assert not auth_service.verificar_clave(hash_, "secreta-124")
    assert not auth_service.requiere_rehash(hash_)


def test_mismo_texto_distinto_hash():
    assert auth_service.hashear_clave("abc") != auth_service.hashear_clave("abc")


@pytest.mark.parametrize("hash_invalido", ["", "x", "$2b$12$noesargon"])
def test_hash_invalido_no_verifica(hash_invalido):
    assert not auth_service.verificar_clave(hash_invalido, "abc")


def test_claves_temporales_aleatorias():
    claves = {auth_service.generar_clave_temporal() for _ in range(50)}
    assert len(claves) == 50
    assert all(len(clave) >= 16 for clave in claves)


async def test_crear_cliente(sesion_bd):
    nombre = nombre_unico()
    usuario, clave = await auth_service.crear_usuario(sesion_bd, f"  {nombre}  ")
    await sesion_bd.commit()

    guardado = await sesion_bd.scalar(select(Usuario).where(Usuario.id == usuario.id))
    assert guardado.usuario == nombre
    assert guardado.rol == "cliente"
    assert guardado.debe_cambiar_clave is True
    assert guardado.activo is True
    assert guardado.hash_password != clave
    assert auth_service.verificar_clave(guardado.hash_password, clave)

    saldo = await sesion_bd.scalar(select(Saldo).where(Saldo.usuario_id == usuario.id))
    assert (saldo.saldo_disponible, saldo.saldo_reservado) == (Decimal(0), Decimal(0))


async def test_crear_admin_sin_cuenta_de_saldo(sesion_bd):
    usuario, _ = await auth_service.crear_usuario(sesion_bd, nombre_unico(), rol="admin")
    await sesion_bd.commit()
    assert usuario.rol == "admin"
    assert usuario.debe_cambiar_clave is True
    assert await sesion_bd.scalar(select(Saldo).where(Saldo.usuario_id == usuario.id)) is None


async def test_usuario_duplicado_no_rompe_la_transaccion(sesion_bd):
    nombre = nombre_unico()
    await auth_service.crear_usuario(sesion_bd, nombre)
    with pytest.raises(UsuarioDuplicado):
        await auth_service.crear_usuario(sesion_bd, nombre)
    # La transacción sigue utilizable tras el duplicado.
    otro, _ = await auth_service.crear_usuario(sesion_bd, nombre_unico())
    await sesion_bd.commit()
    assert otro.id is not None


@pytest.mark.parametrize(("nombre", "rol"), [("", "cliente"), ("   ", "cliente"), ("x", "root")])
async def test_datos_invalidos(sesion_bd, nombre, rol):
    with pytest.raises(DatosUsuarioInvalidos):
        await auth_service.crear_usuario(sesion_bd, nombre, rol=rol)


@pytest.mark.parametrize(
    ("entrada", "esperado"),
    [("  Juan.Perez_1 ", "juan.perez_1"), ("abc", "abc"), ("a-b", "a-b"), ("x" * 30, "x" * 30)],
)
def test_nombre_usuario_valido_se_normaliza(entrada, esperado):
    # RF-07: se guarda en minúsculas.
    assert auth_service.normalizar_nombre_usuario(entrada) == esperado


@pytest.mark.parametrize("entrada", ["ab", "x" * 31, "juan perez", "juan@x", "ñandú", "", None])
def test_nombre_usuario_invalido(entrada):
    with pytest.raises(DatosUsuarioInvalidos):
        auth_service.normalizar_nombre_usuario(entrada)
