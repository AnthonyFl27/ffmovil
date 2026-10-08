"""T-043: validación del Player ID con validar.php (RF-20, RF-26, RF-27)."""

import pytest

from app.services import recarga_service
from app.services.recarga_service import (
    JugadorNoExiste,
    PaqueteNoDisponible,
    PlayerIdInvalido,
    validar_formato_player_id,
)
from app.services.ventasff_client import ClienteVentasFF
from tests.fake_ventasff import SimuladorVentasFF
from tests.utilidades import crear_paquete

BASE = "http://simulador/api/reseller"


@pytest.mark.parametrize("player_id", ["1234", "75807448", "1" * 20, " 75807448 "])
def test_formato_valido(player_id):
    assert validar_formato_player_id(player_id) == player_id.strip()


@pytest.mark.parametrize(
    "player_id", ["123", "1" * 21, "7580744a", "-1234", "12 34", "", "１２３４", None, 75807448]
)
def test_formato_invalido(player_id):
    with pytest.raises(PlayerIdInvalido):
        validar_formato_player_id(player_id)


async def validar(sesion, sim, player_id="75807448", paquete_id=None):
    async with ClienteVentasFF(sim.api_key, BASE, transport=sim.transporte()) as cliente:
        return await recarga_service.validar_jugador(sesion, cliente, player_id, paquete_id)


@pytest.fixture
async def paquete(sesion_bd):
    paquete = await crear_paquete(sesion_bd)
    await sesion_bd.commit()
    return paquete


async def test_ok_devuelve_nickname(sesion_bd, paquete):
    sim = SimuladorVentasFF()
    resultado = await validar(sesion_bd, sim, paquete_id=paquete.paquete_id)
    assert (resultado.estado, resultado.nickname, resultado.advertencia) == (
        "ok",
        "Jugador7448",
        None,
    )
    assert resultado.verificado
    assert ("GET", "/api/reseller/validar.php") in sim.peticiones


async def test_no_existe_bloquea(sesion_bd, paquete):
    sim = SimuladorVentasFF(escenario_validar="no_existe")
    with pytest.raises(JugadorNoExiste):
        await validar(sesion_bd, sim, paquete_id=paquete.paquete_id)


async def test_no_disponible_advierte(sesion_bd, paquete):
    sim = SimuladorVentasFF(escenario_validar="no_disponible")
    resultado = await validar(sesion_bd, sim, paquete_id=paquete.paquete_id)
    assert resultado.estado == "no_disponible"
    assert resultado.advertencia
    assert not resultado.verificado


async def test_fallo_del_validador_advierte(sesion_bd, paquete):
    sim = SimuladorVentasFF()
    sim.api_key = "rv_c_otra"  # el cliente usa otra clave → INVALID_KEY
    async with ClienteVentasFF("rv_c_simulador", BASE, transport=sim.transporte()) as cliente:
        resultado = await recarga_service.validar_jugador(
            sesion_bd, cliente, "75807448", paquete.paquete_id
        )
    assert (resultado.estado, resultado.nickname) == ("error_validador", None)
    assert resultado.advertencia


async def test_formato_invalido_no_llama_al_proveedor(sesion_bd, paquete):
    sim = SimuladorVentasFF()
    with pytest.raises(PlayerIdInvalido):
        await validar(sesion_bd, sim, player_id="12ab", paquete_id=paquete.paquete_id)
    assert sim.peticiones == []


@pytest.mark.parametrize("activo", [False, None])
async def test_paquete_no_disponible(sesion_bd, activo):
    if activo is None:
        paquete_id = -1
    else:
        paquete_id = (await crear_paquete(sesion_bd, activo=False)).paquete_id
        await sesion_bd.commit()
    sim = SimuladorVentasFF()
    with pytest.raises(PaqueteNoDisponible):
        await validar(sesion_bd, sim, paquete_id=paquete_id)
    assert sim.peticiones == []
