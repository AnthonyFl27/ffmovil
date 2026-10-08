"""Pruebas del simulador de VentasFF (RNF-08), sin red."""

import json
import re
from decimal import Decimal
from typing import Any

import httpx
import pytest

from tests.fake_ventasff import SimuladorVentasFF

BASE = "http://simulador/api/reseller"
PETICION_RECARGA = {"paquete_id": 1, "player_id": "123456789"}


@pytest.fixture
def sim() -> SimuladorVentasFF:
    return SimuladorVentasFF()


@pytest.fixture
async def cliente(sim: SimuladorVentasFF):
    async with httpx.AsyncClient(
        transport=sim.transporte(),
        base_url=BASE,
        headers={"Authorization": f"Bearer {sim.api_key}"},
    ) as c:
        yield c


def _json(respuesta: httpx.Response) -> Any:
    """Lee el JSON con montos como Decimal, igual que el cliente real (RNF-04)."""
    return json.loads(respuesta.text, parse_float=Decimal)


async def _recargar(cliente: httpx.AsyncClient, cuerpo: dict[str, Any] | None = None):
    return await cliente.post("recargar.php", json=cuerpo or PETICION_RECARGA)


async def test_saldo(cliente: httpx.AsyncClient):
    resp = await cliente.get("saldo.php")

    assert resp.status_code == 200
    assert _json(resp) == {
        "success": True,
        "data": {"credito": Decimal("100.00"), "currency": "USD", "nombre": "Simulador"},
    }


async def test_productos_con_precios_decimal(cliente: httpx.AsyncClient):
    resp = await cliente.get("productos.php")

    assert resp.status_code == 200
    datos = _json(resp)["data"]
    por_id = {p["paquete_id"]: p for p in datos}
    assert len(datos) >= 3
    assert isinstance(por_id[1]["precio"], Decimal)
    assert por_id[1]["precio"] == Decimal("0.81")
    assert por_id[1]["dato_extra"] is None
    assert por_id[193]["juego"] == "mobile_legends"
    assert por_id[193]["dato_extra"] == "Zone ID"


async def test_sin_cabecera_authorization(sim: SimuladorVentasFF):
    async with httpx.AsyncClient(transport=sim.transporte(), base_url=BASE) as sin_clave:
        resp = await sin_clave.get("saldo.php")

    assert resp.status_code == 401
    assert _json(resp)["code"] == "MISSING_KEY"
    assert _json(resp)["success"] is False


async def test_clave_invalida(cliente: httpx.AsyncClient):
    resp = await cliente.get("saldo.php", headers={"Authorization": "Bearer otra"})

    assert resp.status_code == 401
    assert _json(resp)["code"] == "INVALID_KEY"
    assert isinstance(_json(resp)["error"], str)


@pytest.mark.parametrize(
    ("escenario", "esperado"),
    [
        ("ok", {"valid": True, "nickname": "Jugador6789", "estado": "ok"}),
        ("no_existe", {"valid": False, "nickname": None, "estado": "no_existe"}),
        ("no_disponible", {"valid": False, "nickname": None, "estado": "no_disponible"}),
    ],
)
async def test_validar(sim: SimuladorVentasFF, cliente: httpx.AsyncClient, escenario, esperado):
    sim.escenario_validar = escenario

    resp = await cliente.get("validar.php", params={"player_id": "123456789", "paquete_id": 1})

    assert resp.status_code == 200
    assert _json(resp) == {"success": True, "data": esperado}


async def test_validar_sin_parametro(cliente: httpx.AsyncClient):
    resp = await cliente.get("validar.php", params={"player_id": "123456789"})

    assert resp.status_code == 422
    assert _json(resp)["code"] == "MISSING_FIELD"


async def test_recargar_ok(sim: SimuladorVentasFF, cliente: httpx.AsyncClient):
    resp = await _recargar(cliente)

    assert resp.status_code == 200
    datos = _json(resp)["data"]
    assert _json(resp)["success"] is True
    assert re.fullmatch(r"EV-[0-9A-F]{8}", datos["referencia"])
    assert datos["monto"] == Decimal("0.81")
    assert datos["saldo"] == Decimal("99.19")
    assert datos["player_id"] == "123456789"
    assert datos["nickname"] == "Jugador6789"
    assert sim.credito == Decimal("99.19")
    assert sim.recargas == [
        {
            "referencia": datos["referencia"],
            "paquete_id": 1,
            "player_id": "123456789",
            "monto": Decimal("0.81"),
        }
    ]


async def test_recargar_nickname_null(sim: SimuladorVentasFF, cliente: httpx.AsyncClient):
    sim.escenario_recarga = "nickname_null"

    resp = await _recargar(cliente)

    assert resp.status_code == 200
    assert _json(resp)["data"]["nickname"] is None
    assert sim.credito == Decimal("99.19")
    assert len(sim.recargas) == 1


@pytest.mark.parametrize(
    ("escenario", "status", "codigo"),
    [
        ("PURCHASE_FAILED", 422, "PURCHASE_FAILED"),
        ("BUSY", 409, "BUSY"),
        ("INSUFFICIENT_CREDIT", 422, "INSUFFICIENT_CREDIT"),
        ("INVALID_KEY", 401, "INVALID_KEY"),
        ("RATE_LIMITED", 429, "RATE_LIMITED"),
    ],
)
async def test_recargar_fallos_sin_cobro(
    sim: SimuladorVentasFF, cliente: httpx.AsyncClient, escenario, status, codigo
):
    sim.escenario_recarga = escenario

    resp = await _recargar(cliente)

    assert resp.status_code == status
    assert _json(resp)["success"] is False
    assert _json(resp)["code"] == codigo
    assert sim.credito == Decimal("100.00")
    assert sim.recargas == []


async def test_rate_limited_cabecera_retry_after(
    sim: SimuladorVentasFF, cliente: httpx.AsyncClient
):
    sim.escenario_recarga = "RATE_LIMITED"
    sim.retry_after = 7

    resp = await _recargar(cliente)

    assert resp.status_code == 429
    assert resp.headers["Retry-After"] == "7"


async def test_credito_real_insuficiente(sim: SimuladorVentasFF, cliente: httpx.AsyncClient):
    sim.credito = Decimal("0.10")

    resp = await _recargar(cliente)

    assert resp.status_code == 422
    assert _json(resp)["code"] == "INSUFFICIENT_CREDIT"
    assert sim.credito == Decimal("0.10")
    assert sim.recargas == []


async def test_busy_una_vez_y_luego_ok(sim: SimuladorVentasFF, cliente: httpx.AsyncClient):
    sim.busy_restantes = 1

    primera = await _recargar(cliente)
    segunda = await _recargar(cliente)

    assert primera.status_code == 409
    assert _json(primera)["code"] == "BUSY"
    assert segunda.status_code == 200
    assert sim.busy_restantes == 0
    assert sim.credito == Decimal("99.19")
    assert len(sim.recargas) == 1


@pytest.mark.parametrize(
    "cuerpo",
    [
        {"paquete_id": 1},
        {"paquete_id": 1, "player_id": ""},
        {"player_id": "123456789"},
    ],
)
async def test_recargar_campos_faltantes(
    sim: SimuladorVentasFF, cliente: httpx.AsyncClient, cuerpo
):
    resp = await _recargar(cliente, cuerpo)

    assert resp.status_code == 422
    assert _json(resp)["code"] == "MISSING_FIELD"
    assert _json(resp)["error"] == "Faltan campos: paquete_id y player_id"
    assert sim.recargas == []


async def test_recargar_paquete_desconocido(sim: SimuladorVentasFF, cliente: httpx.AsyncClient):
    resp = await _recargar(cliente, {"paquete_id": 999, "player_id": "123456789"})

    assert resp.status_code == 422
    assert _json(resp)["code"] == "PURCHASE_FAILED"
    assert _json(resp)["error"] == "Paquete no disponible"
    assert sim.recargas == []


async def test_ilegible_cobra_pero_no_es_json(sim: SimuladorVentasFF, cliente: httpx.AsyncClient):
    sim.escenario_recarga = "ilegible"

    resp = await _recargar(cliente)

    assert resp.status_code == 200
    with pytest.raises(json.JSONDecodeError):
        json.loads(resp.text)
    assert sim.credito == Decimal("99.19")
    assert len(sim.recargas) == 1


async def test_timeout_cobra_y_lanza_read_timeout(
    sim: SimuladorVentasFF, cliente: httpx.AsyncClient
):
    sim.escenario_recarga = "timeout"

    with pytest.raises(httpx.ReadTimeout):
        await _recargar(cliente)

    assert sim.credito == Decimal("99.19")
    assert len(sim.recargas) == 1


async def test_timeout_sin_credito_responde_error(
    sim: SimuladorVentasFF, cliente: httpx.AsyncClient
):
    sim.escenario_recarga = "timeout"
    sim.credito = Decimal(0)

    resp = await _recargar(cliente)

    assert resp.status_code == 422
    assert _json(resp)["code"] == "INSUFFICIENT_CREDIT"
    assert sim.recargas == []


async def test_error_conexion_no_cobra(sim: SimuladorVentasFF, cliente: httpx.AsyncClient):
    sim.escenario_recarga = "error_conexion"

    with pytest.raises(httpx.ConnectError):
        await _recargar(cliente)

    assert sim.credito == Decimal("100.00")
    assert sim.recargas == []
    assert ("POST", "/api/reseller/recargar.php") in sim.peticiones


async def test_peticiones_registradas(sim: SimuladorVentasFF, cliente: httpx.AsyncClient):
    await cliente.get("saldo.php")
    await cliente.get("productos.php")
    await _recargar(cliente)

    assert sim.peticiones == [
        ("GET", "/api/reseller/saldo.php"),
        ("GET", "/api/reseller/productos.php"),
        ("POST", "/api/reseller/recargar.php"),
    ]
