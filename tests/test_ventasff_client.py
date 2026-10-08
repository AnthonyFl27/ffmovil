"""T-020: cliente VentasFF contra respuestas simuladas con respx (RNF-01, spec sec. 9)."""

import json
import logging
from decimal import Decimal

import httpx
import pytest
import respx

from app.services.ventasff_client import (
    URL_BASE,
    ClienteVentasFF,
    ErrorAPI,
    Producto,
    RecargaRealizada,
    SaldoProveedor,
    Validacion,
)

CLAVE = "rv_c_prueba_cliente"


def respuesta(status: int, texto: str, **kwargs) -> httpx.Response:
    return httpx.Response(status, content=texto.encode(), **kwargs)


@pytest.fixture
async def cliente():
    async with ClienteVentasFF(CLAVE) as c:
        yield c


@pytest.fixture
def api():
    with respx.mock(base_url=URL_BASE, assert_all_called=False) as mock:
        yield mock


async def test_saldo_con_bearer_y_decimal_exacto(cliente, api):
    ruta = api.get("/saldo.php").mock(
        return_value=respuesta(
            200, '{"success":true,"data":{"credito":25.50,"currency":"USD","nombre":"Nestor"}}'
        )
    )
    saldo = await cliente.saldo()
    assert saldo == SaldoProveedor(credito=Decimal("25.50"), currency="USD", nombre="Nestor")
    assert isinstance(saldo.credito, Decimal)
    assert ruta.calls.last.request.headers["Authorization"] == f"Bearer {CLAVE}"


async def test_credito_entero(cliente, api):
    api.get("/saldo.php").mock(
        return_value=respuesta(
            200, '{"success":true,"data":{"credito":66,"currency":"USD","nombre":"N"}}'
        )
    )
    assert (await cliente.saldo()).credito == Decimal(66)


async def test_productos(cliente, api):
    api.get("/productos.php").mock(
        return_value=respuesta(
            200,
            '{"success":true,"data":['
            '{"paquete_id":1,"nombre":"110 Diamantes","juego":"free_fire","diamantes":110,'
            '"precio":0.81,"currency":"USD","dato_extra":null},'
            '{"paquete_id":193,"nombre":"56 Diamantes","juego":"mobile_legends","diamantes":56,'
            '"precio":1.10,"currency":"USD","dato_extra":"Zone ID"}]}',
        )
    )
    productos = await cliente.productos()
    assert productos[0] == Producto(
        1, "110 Diamantes", "free_fire", 110, Decimal("0.81"), "USD", None
    )
    assert productos[1].dato_extra == "Zone ID"
    assert productos[1].precio == Decimal("1.10")


async def test_validar_envia_player_y_paquete(cliente, api):
    ruta = api.get("/validar.php").mock(
        return_value=respuesta(
            200, '{"success":true,"data":{"valid":true,"nickname":"Jugador","estado":"ok"}}'
        )
    )
    assert await cliente.validar("75807448", 1) == Validacion(True, "Jugador", "ok")
    assert dict(ruta.calls.last.request.url.params) == {"player_id": "75807448", "paquete_id": "1"}


async def test_recargar_cuerpo_exacto_y_timeout_90(cliente, api):
    ruta = api.post("/recargar.php").mock(
        return_value=respuesta(
            200,
            '{"success":true,"data":{"referencia":"EV-9B5F34F9","monto":0.81,"saldo":24.30,'
            '"player_id":"75807448","nickname":null}}',
        )
    )
    recarga = await cliente.recargar(1, "75807448")
    assert recarga == RecargaRealizada(
        "EV-9B5F34F9", Decimal("0.81"), Decimal("24.30"), "75807448", None
    )
    peticion = ruta.calls.last.request
    # recargar.php no acepta otros campos (spec sec. 9).
    assert json.loads(peticion.content) == {"paquete_id": 1, "player_id": "75807448"}
    assert peticion.extensions["timeout"] == {
        "connect": 15.0,
        "read": 90.0,
        "write": 90.0,
        "pool": 90.0,
    }


async def test_timeouts_generales(cliente, api):
    ruta = api.get("/saldo.php").mock(
        return_value=respuesta(
            200, '{"success":true,"data":{"credito":1,"currency":"USD","nombre":"N"}}'
        )
    )
    await cliente.saldo()
    timeout = ruta.calls.last.request.extensions["timeout"]
    assert (timeout["connect"], timeout["read"]) == (15.0, 30.0)


@pytest.mark.parametrize(
    ("status", "code", "mensaje"),
    [
        (401, "INVALID_KEY", "Key inválida"),
        (409, "BUSY", "Ya tienes una recarga en curso"),
        (422, "PURCHASE_FAILED", "Paquete no disponible"),
        (422, "INSUFFICIENT_CREDIT", "Sin crédito"),
    ],
)
async def test_error_de_api(cliente, api, status, code, mensaje):
    api.post("/recargar.php").mock(
        return_value=respuesta(
            status, json.dumps({"success": False, "error": mensaje, "code": code})
        )
    )
    with pytest.raises(ErrorAPI) as error:
        await cliente.recargar(1, "75807448")
    assert (error.value.code, error.value.mensaje, error.value.estado_http) == (
        code,
        mensaje,
        status,
    )


async def test_la_clave_no_aparece_en_logs(cliente, api, caplog):
    api.get("/saldo.php").mock(
        return_value=respuesta(
            200, '{"success":true,"data":{"credito":1,"currency":"USD","nombre":"N"}}'
        )
    )
    with caplog.at_level(logging.DEBUG):
        await cliente.saldo()
    assert caplog.records
    assert CLAVE not in caplog.text
