"""El cliente VentasFF contra el simulador: clasificación y cobro por escenario (RNF-08)."""

from decimal import Decimal

import pytest

from app.services.ventasff_client import Clasificacion, ClienteVentasFF, ErrorVentasFF, clasificar
from tests.fake_ventasff import SimuladorVentasFF

BASE = "http://simulador/api/reseller"

ESPERADO = {
    # escenario: (clasificación, ¿el proveedor cobró?)
    "ok": (Clasificacion.EXITO, True),
    "nickname_null": (Clasificacion.EXITO, True),
    "PURCHASE_FAILED": (Clasificacion.ERROR_API, False),
    "BUSY": (Clasificacion.ERROR_API, False),
    "INSUFFICIENT_CREDIT": (Clasificacion.ERROR_API, False),
    "INVALID_KEY": (Clasificacion.ERROR_API, False),
    "RATE_LIMITED": (Clasificacion.ERROR_API, False),
    "timeout": (Clasificacion.INCIERTO, True),
    "ilegible": (Clasificacion.INCIERTO, True),
    "error_conexion": (Clasificacion.ERROR_PREVIO, False),
}


@pytest.mark.parametrize("escenario", list(ESPERADO))
async def test_recarga_por_escenario(escenario):
    sim = SimuladorVentasFF(escenario_recarga=escenario)
    async with ClienteVentasFF(sim.api_key, BASE, transport=sim.transporte()) as cliente:
        try:
            resultado = await cliente.recargar(1, "75807448")
        except ErrorVentasFF as error:
            resultado = error
    clasificacion, cobrado = ESPERADO[escenario]
    assert clasificar(resultado) == clasificacion
    assert bool(sim.recargas) is cobrado
    if escenario == "nickname_null":
        assert resultado.nickname is None


async def test_consultas_contra_simulador():
    sim = SimuladorVentasFF(credito=Decimal("12.34"))
    async with ClienteVentasFF(sim.api_key, BASE, transport=sim.transporte()) as cliente:
        assert (await cliente.saldo()).credito == Decimal("12.34")
        productos = await cliente.productos()
        assert productos[0].precio == Decimal("0.50")
        validacion = await cliente.validar("75807448", 1)
        assert (validacion.estado, validacion.nickname) == ("ok", "Jugador7448")
