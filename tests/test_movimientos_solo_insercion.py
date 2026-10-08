"""T-011: `movimientos` no admite UPDATE, DELETE ni TRUNCATE (RF-42)."""

import pytest
from sqlalchemy import delete, func, select, text, update
from sqlalchemy.exc import DBAPIError

from app.models import Movimiento
from tests.test_modelo_contable import crear_usuario, movimiento


@pytest.fixture
async def movimiento_guardado(sesion_bd):
    usuario = await crear_usuario(sesion_bd)
    registro = movimiento(usuario.id)
    sesion_bd.add(registro)
    await sesion_bd.commit()
    # Solo el id: el rollback de la prueba expira los atributos del objeto.
    return registro.id


@pytest.mark.parametrize(
    "sentencia",
    [
        lambda id_: update(Movimiento).where(Movimiento.id == id_).values(nota="cambiada"),
        lambda id_: delete(Movimiento).where(Movimiento.id == id_),
        lambda _: text("TRUNCATE movimientos"),
    ],
    ids=["update", "delete", "truncate"],
)
async def test_movimiento_no_se_modifica(sesion_bd, movimiento_guardado, sentencia):
    with pytest.raises(DBAPIError, match="solo inserción"):
        await sesion_bd.execute(sentencia(movimiento_guardado))
    await sesion_bd.rollback()

    nota = await sesion_bd.scalar(
        select(Movimiento.nota).where(Movimiento.id == movimiento_guardado)
    )
    assert nota == "transferencia"


async def test_insercion_permitida(sesion_bd, movimiento_guardado):
    total = await sesion_bd.scalar(
        select(func.count()).select_from(Movimiento).where(Movimiento.id == movimiento_guardado)
    )
    assert total == 1
