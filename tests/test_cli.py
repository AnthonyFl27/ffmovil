"""T-016: comando para crear el primer admin (RF-02)."""

import uuid

import pytest
from sqlalchemy import select, update

from app.cli import AdminExistente, crear_admin, crear_primer_admin
from app.db import crear_fabrica_sesiones
from app.models import Usuario
from app.services import auth_service
from tests.utilidades import crear_usuario


async def test_crea_el_primer_admin(sesion_bd):
    # El esquema `test` es compartido: dentro de esta transacción (que se revierte)
    # se simula que todavía no hay admins.
    await sesion_bd.execute(update(Usuario).where(Usuario.rol == "admin").values(rol="cliente"))
    nombre = f"admin_{uuid.uuid4().hex[:8]}"

    usuario, clave = await crear_primer_admin(sesion_bd, nombre)

    guardado = await sesion_bd.scalar(select(Usuario).where(Usuario.id == usuario.id))
    assert (guardado.usuario, guardado.rol, guardado.debe_cambiar_clave) == (nombre, "admin", True)
    assert auth_service.verificar_clave(guardado.hash_password, clave)
    await sesion_bd.rollback()


async def test_rechaza_si_ya_hay_admin(sesion_bd):
    await crear_usuario(sesion_bd, rol="admin")
    with pytest.raises(AdminExistente):
        await crear_primer_admin(sesion_bd, "otro_admin")
    await sesion_bd.rollback()


async def test_comando_informa_error_sin_crear(motor_bd, sesion_bd, admin_id, capsys):
    nombre = f"admin_{uuid.uuid4().hex[:8]}"
    codigo = await crear_admin(crear_fabrica_sesiones(motor_bd), nombre)

    salida = capsys.readouterr()
    assert codigo == 1
    assert "Ya existe un admin" in salida.err
    assert "Clave temporal" not in salida.out
    assert await sesion_bd.scalar(select(Usuario).where(Usuario.usuario == nombre)) is None
