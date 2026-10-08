"""T-031: precio de venta, aviso bajo costo y activación (RF-11, RF-12, RNF-04)."""

import random
from decimal import Decimal

import pytest

from app.models import Paquete
from app.services import catalogo
from app.services.catalogo import PaqueteInexistente, PaqueteSinPrecio, PrecioInvalido

D = Decimal


@pytest.fixture
async def paquete_id(sesion_bd):
    """Paquete nuevo de costo 0.50, inactivo y sin precio de venta."""
    nuevo = Paquete(
        paquete_id=random.randint(100_000, 999_999_999),
        juego="free_fire",
        nombre="110 Diamantes",
        diamantes=110,
        precio_costo=D("0.50"),
    )
    sesion_bd.add(nuevo)
    await sesion_bd.commit()
    return nuevo.paquete_id


@pytest.mark.parametrize(
    ("precio", "bajo_costo"),
    [(D("0.75"), False), (D("0.51"), False), (D("0.50"), True), (D("0.49"), True)],
)
async def test_fijar_precio_avisa_si_no_supera_el_costo(sesion_bd, paquete_id, precio, bajo_costo):
    resultado = await catalogo.fijar_precio_venta(sesion_bd, paquete_id, precio)
    await sesion_bd.commit()
    assert resultado.paquete.precio_venta == precio
    assert resultado.bajo_costo is bajo_costo
    # El aviso no impide guardar ni activa el paquete.
    assert resultado.paquete.activo is False


@pytest.mark.parametrize(
    "precio",
    [0.75, 1, D("0"), D("0.00"), D("-0.75"), D("0.751"), D("NaN"), D("1E+10"), "0.75"],
    ids=["float", "int", "cero", "cero_2", "negativo", "3_decimales", "nan", "excede", "texto"],
)
async def test_precio_invalido(sesion_bd, paquete_id, precio):
    with pytest.raises(PrecioInvalido):
        await catalogo.fijar_precio_venta(sesion_bd, paquete_id, precio)
    await sesion_bd.rollback()


def test_precio_se_normaliza_a_2_decimales():
    assert str(catalogo.validar_precio_venta(D("1.5"))) == "1.50"


async def test_no_se_activa_sin_precio(sesion_bd, paquete_id):
    with pytest.raises(PaqueteSinPrecio):
        await catalogo.activar(sesion_bd, paquete_id)
    await sesion_bd.rollback()


async def test_activar_y_desactivar(sesion_bd, paquete_id):
    await catalogo.fijar_precio_venta(sesion_bd, paquete_id, D("0.75"))
    paquete = await catalogo.activar(sesion_bd, paquete_id)
    await sesion_bd.commit()
    assert paquete.activo is True
    paquete = await catalogo.desactivar(sesion_bd, paquete_id)
    await sesion_bd.commit()
    assert paquete.activo is False
    assert paquete.precio_venta == D("0.75")


async def test_paquete_inexistente(sesion_bd):
    with pytest.raises(PaqueteInexistente):
        await catalogo.fijar_precio_venta(sesion_bd, -1, D("1.00"))
    with pytest.raises(PaqueteInexistente):
        await catalogo.activar(sesion_bd, -1)
    await sesion_bd.rollback()


@pytest.mark.parametrize(
    ("costo", "venta", "esperado"),
    [(D("0.50"), None, False), (D("0.50"), D("0.75"), False), (D("0.50"), D("0.50"), True)],
)
def test_precio_bajo_costo(costo, venta, esperado):
    paquete = Paquete(precio_costo=costo, precio_venta=venta)
    assert catalogo.precio_bajo_costo(paquete) is esperado
