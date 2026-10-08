"""T-030: tablas `paquetes` y `config` (RF-10 a RF-12)."""

import random
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.models import Config, Paquete


def paquete(**cambios) -> Paquete:
    datos = {
        "paquete_id": random.randint(100_000, 999_999_999),
        "juego": "free_fire",
        "nombre": "110 Diamantes",
        "diamantes": 110,
        "precio_costo": Decimal("0.50"),
    } | cambios
    return Paquete(**datos)


async def test_paquete_nuevo_inactivo_sin_precio(sesion_bd):
    nuevo = paquete()
    sesion_bd.add(nuevo)
    await sesion_bd.flush()
    await sesion_bd.refresh(nuevo)
    assert nuevo.activo is False
    assert nuevo.precio_venta is None
    assert nuevo.actualizado_en.tzinfo is not None
    await sesion_bd.rollback()


async def test_activo_con_precio_de_venta(sesion_bd):
    sesion_bd.add(paquete(precio_venta=Decimal("0.75"), activo=True))
    await sesion_bd.flush()
    await sesion_bd.rollback()


@pytest.mark.parametrize(
    ("cambios", "restriccion"),
    [
        ({"activo": True}, "ck_paquetes_activo_con_precio"),
        ({"precio_venta": Decimal("0.00")}, "ck_paquetes_precio_venta_positivo"),
        ({"precio_venta": Decimal("-1.00")}, "ck_paquetes_precio_venta_positivo"),
        ({"precio_costo": Decimal("-0.01")}, "ck_paquetes_precio_costo_no_negativo"),
    ],
)
async def test_paquete_invalido(sesion_bd, cambios, restriccion):
    sesion_bd.add(paquete(**cambios))
    with pytest.raises(IntegrityError, match=restriccion):
        await sesion_bd.flush()
    await sesion_bd.rollback()


async def test_config_clave_valor(sesion_bd):
    sesion_bd.add(Config(clave="prueba_t030", valor="5.00"))
    await sesion_bd.flush()
    valor = await sesion_bd.scalar(select(Config.valor).where(Config.clave == "prueba_t030"))
    assert valor == "5.00"
    await sesion_bd.rollback()
