"""T-010: restricciones del modelo contable (RN-01, RNF-04)."""

from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.models import Auditoria, Movimiento, Saldo, Usuario
from tests.utilidades import crear_usuario, nuevo_usuario


def movimiento(usuario_id: int, **cambios) -> Movimiento:
    datos = {
        "usuario_id": usuario_id,
        "tipo": "abono",
        "monto": Decimal("10.00"),
        "saldo_disponible_resultante": Decimal("10.00"),
        "saldo_reservado_resultante": Decimal("0.00"),
        "nota": "transferencia",
    } | cambios
    return Movimiento(**datos)


async def test_valores_por_defecto(sesion_bd):
    usuario = await crear_usuario(sesion_bd)
    sesion_bd.add(Saldo(usuario_id=usuario.id))
    await sesion_bd.flush()
    await sesion_bd.refresh(usuario)
    saldo = await sesion_bd.scalar(select(Saldo).where(Saldo.usuario_id == usuario.id))
    assert usuario.debe_cambiar_clave is True
    assert usuario.activo is True
    assert usuario.creado_en.tzinfo is not None
    assert saldo.saldo_disponible == Decimal("0.00")
    assert isinstance(saldo.saldo_disponible, Decimal)
    await sesion_bd.rollback()


async def test_rol_invalido(sesion_bd):
    sesion_bd.add(nuevo_usuario(rol="superusuario"))
    with pytest.raises(IntegrityError, match="ck_usuarios_rol"):
        await sesion_bd.flush()
    await sesion_bd.rollback()


async def test_usuario_unico(sesion_bd):
    usuario = await crear_usuario(sesion_bd)
    sesion_bd.add(Usuario(usuario=usuario.usuario, hash_password="x", rol="cliente"))
    with pytest.raises(IntegrityError, match="uq_usuarios_usuario"):
        await sesion_bd.flush()
    await sesion_bd.rollback()


@pytest.mark.parametrize("columna", ["saldo_disponible", "saldo_reservado"])
async def test_saldo_no_negativo(sesion_bd, columna):
    usuario = await crear_usuario(sesion_bd)
    sesion_bd.add(Saldo(usuario_id=usuario.id, **{columna: Decimal("-0.01")}))
    with pytest.raises(IntegrityError, match="no_negativo"):
        await sesion_bd.flush()
    await sesion_bd.rollback()


@pytest.mark.parametrize(
    ("cambios", "restriccion"),
    [
        ({"tipo": "regalo"}, "ck_movimientos_tipo"),
        ({"tipo": "cargo", "monto": Decimal("-1.00")}, "ck_movimientos_monto_positivo"),
        ({"tipo": "reserva", "monto": Decimal("0.00")}, "ck_movimientos_monto_positivo"),
        ({"tipo": "ajuste", "monto": Decimal("0.00")}, "ck_movimientos_ajuste_no_cero"),
        ({"tipo": "abono", "nota": None}, "ck_movimientos_nota_obligatoria"),
        ({"tipo": "ajuste", "nota": "   "}, "ck_movimientos_nota_obligatoria"),
        ({"saldo_disponible_resultante": Decimal(-1)}, "ck_movimientos_disponible_no_negativo"),
        ({"saldo_reservado_resultante": Decimal(-1)}, "ck_movimientos_reservado_no_negativo"),
    ],
)
async def test_movimiento_invalido(sesion_bd, cambios, restriccion):
    usuario = await crear_usuario(sesion_bd)
    sesion_bd.add(movimiento(usuario.id, **cambios))
    with pytest.raises(IntegrityError, match=restriccion):
        await sesion_bd.flush()
    await sesion_bd.rollback()


async def test_movimientos_validos(sesion_bd):
    usuario = await crear_usuario(sesion_bd)
    sesion_bd.add_all(
        [
            movimiento(usuario.id),
            movimiento(usuario.id, tipo="ajuste", monto=Decimal("-2.50"), nota="corrección"),
            movimiento(usuario.id, tipo="reserva", monto=Decimal("0.50"), nota=None),
        ]
    )
    await sesion_bd.flush()
    await sesion_bd.rollback()


async def test_auditoria_guarda_detalle_e_ip(sesion_bd):
    usuario = await crear_usuario(sesion_bd)
    registro = Auditoria(
        usuario_id=usuario.id, accion="abono", detalle={"monto": "10.00"}, ip="192.0.2.1"
    )
    sesion_bd.add(registro)
    await sesion_bd.flush()
    await sesion_bd.refresh(registro)
    assert registro.detalle == {"monto": "10.00"}
    assert str(registro.ip) == "192.0.2.1"
    await sesion_bd.rollback()
