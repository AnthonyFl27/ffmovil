"""T-045: Fase B, candado global, limitador, crédito y BUSY (RF-23, RN-05 a RN-08)."""

import asyncio
from decimal import Decimal

import pytest
from sqlalchemy import text

from app.services.limitador import LimitadorTasa
from app.services.recarga_service import (
    ALERTA_CREDITO,
    CANDADO_RECARGAS,
    MENSAJE_PROVEEDOR_OCUPADO,
    SEGUNDOS_REINTENTO_BUSY,
    llamar_proveedor,
)
from app.services.ventasff_client import Clasificacion, ClienteVentasFF
from tests.fake_ventasff import SimuladorVentasFF

BASE = "http://simulador/api/reseller"
RECARGAR = ("POST", "/api/reseller/recargar.php")


class Esperas:
    def __init__(self):
        self.valores: list[float] = []

    async def __call__(self, segundos: float) -> None:
        self.valores.append(segundos)


async def llamar(motor, sim, limitador=None, dormir=None, precio_costo=Decimal("0.81")):
    async with ClienteVentasFF(sim.api_key, BASE, transport=sim.transporte()) as cliente:
        return await llamar_proveedor(
            motor,
            cliente,
            limitador or LimitadorTasa(8),
            paquete_id=1,
            player_id="75807448",
            precio_costo=precio_costo,
            dormir=dormir or Esperas(),
        )


async def test_exito_verifica_credito_antes_de_recargar(motor_bd):
    sim = SimuladorVentasFF()
    resultado = await llamar(motor_bd, sim)
    assert resultado.clasificacion == Clasificacion.EXITO
    assert resultado.recarga.referencia.startswith("EV-")
    assert sim.peticiones == [("GET", "/api/reseller/saldo.php"), RECARGAR]


async def test_credito_insuficiente_no_recarga(motor_bd):
    sim = SimuladorVentasFF(credito=Decimal("0.80"))
    resultado = await llamar(motor_bd, sim)
    assert resultado.clasificacion == Clasificacion.ERROR_PREVIO
    assert (resultado.error_code, resultado.alerta) == ("SIN_CREDITO_PROVEEDOR", ALERTA_CREDITO)
    assert RECARGAR not in sim.peticiones
    assert sim.recargas == []


async def test_busy_reintenta_una_vez_tras_3_segundos(motor_bd):
    sim = SimuladorVentasFF(busy_restantes=1)
    esperas = Esperas()
    resultado = await llamar(motor_bd, sim, dormir=esperas)
    assert resultado.clasificacion == Clasificacion.EXITO
    assert esperas.valores == [SEGUNDOS_REINTENTO_BUSY]
    assert sim.peticiones.count(RECARGAR) == 2


async def test_busy_persistente_falla_como_proveedor_ocupado(motor_bd):
    sim = SimuladorVentasFF(escenario_recarga="BUSY")
    esperas = Esperas()
    resultado = await llamar(motor_bd, sim, dormir=esperas)
    assert resultado.clasificacion == Clasificacion.ERROR_API
    assert (resultado.error_code, resultado.motivo) == ("BUSY", MENSAJE_PROVEEDOR_OCUPADO)
    assert esperas.valores == [SEGUNDOS_REINTENTO_BUSY]
    assert sim.peticiones.count(RECARGAR) == 2
    assert sim.recargas == []


async def test_usa_el_limitador(motor_bd):
    class LimitadorContado(LimitadorTasa):
        usos = 0

        async def adquirir(self) -> float:
            LimitadorContado.usos += 1
            return await super().adquirir()

    await llamar(motor_bd, SimuladorVentasFF(), limitador=LimitadorContado(8))
    assert LimitadorContado.usos == 1


async def test_candado_global_serializa_las_recargas(motor_bd):
    """RN-05: mientras otra conexión tiene el candado, no se llama al proveedor."""
    sim = SimuladorVentasFF()
    async with motor_bd.connect() as otra:
        await otra.execute(text("SELECT pg_advisory_lock(:c)"), {"c": CANDADO_RECARGAS})
        await otra.commit()
        tarea = asyncio.create_task(llamar(motor_bd, sim))
        await asyncio.sleep(2)
        assert sim.peticiones == []
        assert not tarea.done()
        await otra.execute(text("SELECT pg_advisory_unlock(:c)"), {"c": CANDADO_RECARGAS})
        await otra.commit()
    resultado = await asyncio.wait_for(tarea, timeout=30)
    assert resultado.clasificacion == Clasificacion.EXITO


async def test_libera_el_candado_al_terminar(motor_bd):
    await llamar(motor_bd, SimuladorVentasFF(escenario_recarga="timeout"))
    async with motor_bd.connect() as conexion:
        libre = await conexion.scalar(
            text("SELECT pg_try_advisory_lock(:c)"), {"c": CANDADO_RECARGAS}
        )
        assert libre is True
        await conexion.execute(text("SELECT pg_advisory_unlock(:c)"), {"c": CANDADO_RECARGAS})
        await conexion.commit()


@pytest.mark.parametrize(
    ("escenario", "clasificacion", "codigo", "alerta"),
    [
        ("PURCHASE_FAILED", Clasificacion.ERROR_API, "PURCHASE_FAILED", None),
        ("INSUFFICIENT_CREDIT", Clasificacion.ERROR_API, "INSUFFICIENT_CREDIT", "credito"),
        ("INVALID_KEY", Clasificacion.ERROR_API, "INVALID_KEY", "cuenta"),
        ("RATE_LIMITED", Clasificacion.ERROR_API, "RATE_LIMITED", None),
        ("error_conexion", Clasificacion.ERROR_PREVIO, "SIN_CONEXION", None),
        ("timeout", Clasificacion.INCIERTO, None, None),
        ("ilegible", Clasificacion.INCIERTO, None, None),
    ],
)
async def test_clasificacion_por_escenario(motor_bd, escenario, clasificacion, codigo, alerta):
    resultado = await llamar(motor_bd, SimuladorVentasFF(escenario_recarga=escenario))
    assert (resultado.clasificacion, resultado.error_code, resultado.alerta) == (
        clasificacion,
        codigo,
        alerta,
    )
    if clasificacion != Clasificacion.INCIERTO:
        assert resultado.motivo
