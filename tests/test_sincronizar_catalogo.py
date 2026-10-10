"""T-032, T-115: sincronización del catálogo contra el simulador (RF-10, RF-14, CA-08)."""

import random
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.models import Paquete
from app.services import catalogo
from app.services.ventasff_client import ClienteVentasFF, ErrorAPI
from tests.fake_ventasff import SimuladorVentasFF

D = Decimal
BASE = "http://simulador/api/reseller"


def producto(paquete_id, precio, juego="free_fire", nombre=None, diamantes=100):
    return {
        "paquete_id": paquete_id,
        "nombre": nombre or f"Paquete {paquete_id}",
        "juego": juego,
        "diamantes": diamantes,
        "precio": precio,
        "currency": "USD",
        "dato_extra": None if juego == "free_fire" else "Zone ID",
    }


@pytest.fixture
def ids():
    """Ids propios de la prueba: el esquema `test` se comparte en toda la sesión."""
    base = random.randint(10_000_000, 900_000_000)
    return base, base + 1, base + 2


async def sincronizar(sesion, sim) -> catalogo.ResumenSincronizacion:
    async with ClienteVentasFF(sim.api_key, BASE, transport=sim.transporte()) as cliente:
        resumen = await catalogo.sincronizar_catalogo(sesion, cliente)
    await sesion.commit()
    return resumen


async def leer(sesion, paquete_id) -> Paquete | None:
    return await sesion.scalar(
        select(Paquete)
        .where(Paquete.paquete_id == paquete_id)
        .execution_options(populate_existing=True)
    )


async def test_crea_solo_free_fire_inactivos_sin_precio(sesion_bd, ids):
    a, b, ml = ids
    sim = SimuladorVentasFF(
        productos=[
            producto(a, D("0.50"), nombre="110 Diamantes", diamantes=110),
            producto(b, D("2.40")),
            producto(ml, D("1.10"), juego="mobile_legends"),
        ]
    )
    resumen = await sincronizar(sesion_bd, sim)

    assert (resumen.recibidos, resumen.nuevos) == (2, 2)
    nuevo = await leer(sesion_bd, a)
    assert (nuevo.nombre, nuevo.diamantes, nuevo.precio_costo) == ("110 Diamantes", 110, D("0.50"))
    assert (nuevo.juego, nuevo.activo, nuevo.precio_venta) == ("free_fire", False, None)
    assert await leer(sesion_bd, ml) is None


async def test_cambio_de_costo_no_toca_precio_venta_ni_activo(sesion_bd, ids):
    a, b, _ = ids
    sim = SimuladorVentasFF(productos=[producto(a, D("0.50")), producto(b, D("2.40"))])
    await sincronizar(sesion_bd, sim)
    await catalogo.fijar_precio_venta(sesion_bd, a, D("0.75"))
    await catalogo.activar(sesion_bd, a)
    await catalogo.fijar_precio_venta(sesion_bd, b, D("3.00"))
    await sesion_bd.commit()

    sim.productos = [
        producto(a, D("0.95"), nombre="110 Diamantes nuevo"),
        producto(b, D("2.40")),
    ]
    resumen = await sincronizar(sesion_bd, sim)

    paquete = await leer(sesion_bd, a)
    assert (paquete.precio_costo, paquete.nombre) == (D("0.95"), "110 Diamantes nuevo")
    assert (paquete.precio_venta, paquete.activo) == (D("0.75"), True)
    assert (resumen.nuevos, resumen.actualizados) == (0, 1)
    # RF-14: ahora 0.75 <= 0.95, se marca; b sigue por encima del costo.
    assert a in resumen.bajo_costo
    assert b not in resumen.bajo_costo


async def test_sin_cambios_no_cuenta_actualizados(sesion_bd, ids):
    a, _, _ = ids
    sim = SimuladorVentasFF(productos=[producto(a, D("0.50"))])
    await sincronizar(sesion_bd, sim)
    resumen = await sincronizar(sesion_bd, sim)
    assert (resumen.nuevos, resumen.actualizados) == (0, 0)


async def test_ausente_se_desactiva_y_no_se_reactiva_solo(sesion_bd, ids):
    a, b, _ = ids
    sim = SimuladorVentasFF(productos=[producto(a, D("0.50")), producto(b, D("2.40"))])
    await sincronizar(sesion_bd, sim)
    await catalogo.fijar_precio_venta(sesion_bd, b, D("3.00"))
    await catalogo.activar(sesion_bd, b)
    await sesion_bd.commit()

    sim.productos = [producto(a, D("0.50"))]
    resumen = await sincronizar(sesion_bd, sim)
    paquete = await leer(sesion_bd, b)
    assert (paquete.activo, paquete.precio_venta) == (False, D("3.00"))
    assert resumen.desactivados >= 1

    # Si vuelve a aparecer, queda inactivo hasta que el admin lo active.
    sim.productos = [producto(a, D("0.50")), producto(b, D("2.40"))]
    await sincronizar(sesion_bd, sim)
    assert (await leer(sesion_bd, b)).activo is False


async def test_error_de_api_no_modifica_nada(sesion_bd, ids):
    a, _, _ = ids
    sim = SimuladorVentasFF(productos=[producto(a, D("0.50"))])
    await sincronizar(sesion_bd, sim)

    sim.productos = [producto(a, D("9.99"))]
    sim.api_key = "rv_c_otra"  # el cliente sigue usando la clave anterior → INVALID_KEY
    async with ClienteVentasFF("rv_c_simulador", BASE, transport=sim.transporte()) as cliente:
        with pytest.raises(ErrorAPI):
            await catalogo.sincronizar_catalogo(sesion_bd, cliente)
    await sesion_bd.rollback()
    assert (await leer(sesion_bd, a)).precio_costo == D("0.50")


@pytest.mark.parametrize("otros_juegos", [False, True], ids=["lista_vacia", "solo_otros_juegos"])
async def test_catalogo_vacio_no_modifica_nada(sesion_bd, ids, otros_juegos):
    """RF-10, CHG-018: sin paquetes free_fire no se desactiva ni se actualiza nada."""
    a, b, ml = ids
    sim = SimuladorVentasFF(productos=[producto(a, D("0.50")), producto(b, D("2.40"))])
    await sincronizar(sesion_bd, sim)
    await catalogo.fijar_precio_venta(sesion_bd, b, D("3.00"))
    await catalogo.activar(sesion_bd, b)
    await sesion_bd.commit()

    sim.productos = [producto(ml, D("1.00"), juego="mobile_legends")] if otros_juegos else []
    resumen = await sincronizar(sesion_bd, sim)

    assert resumen.catalogo_vacio is True
    assert (resumen.recibidos, resumen.nuevos, resumen.actualizados, resumen.desactivados) == (
        0,
        0,
        0,
        0,
    )
    paquete = await leer(sesion_bd, b)
    assert (paquete.activo, paquete.precio_venta, paquete.precio_costo) == (
        True,
        D("3.00"),
        D("2.40"),
    )
    assert await leer(sesion_bd, ml) is None


async def test_lista_parcial_sigue_desactivando_ausentes(sesion_bd, ids):
    a, b, _ = ids
    sim = SimuladorVentasFF(productos=[producto(a, D("0.50")), producto(b, D("2.40"))])
    await sincronizar(sesion_bd, sim)
    await catalogo.fijar_precio_venta(sesion_bd, b, D("3.00"))
    await catalogo.activar(sesion_bd, b)
    await sesion_bd.commit()

    sim.productos = [producto(a, D("0.50"))]
    resumen = await sincronizar(sesion_bd, sim)

    assert resumen.catalogo_vacio is False
    assert (await leer(sesion_bd, b)).activo is False
