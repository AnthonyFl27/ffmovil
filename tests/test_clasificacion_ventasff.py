"""T-021: clasificación de resultados de VentasFF (RF-24, RN-04, plan 4.5)."""

import httpx
import pytest
import respx

from app.services.ventasff_client import (
    URL_BASE,
    Clasificacion,
    ClienteVentasFF,
    ErrorAPI,
    ErrorVentasFF,
    clasificar,
)

OK = (
    '{"success":true,"data":{"referencia":"EV-9B5F34F9","monto":0.50,"saldo":24.30,'
    '"player_id":"75807448","nickname":"Jugador"}}'
)


def cuerpo(status: int, texto: str):
    return httpx.Response(status, content=texto.encode())


CASOS = [
    # (id, respuesta o excepción de transporte, clasificación esperada)
    ("exito", cuerpo(200, OK), Clasificacion.EXITO),
    (
        "exito_nickname_null",
        cuerpo(200, OK.replace('"Jugador"', "null")),
        Clasificacion.EXITO,
    ),
    (
        "purchase_failed",
        cuerpo(422, '{"success":false,"error":"Paquete no disponible","code":"PURCHASE_FAILED"}'),
        Clasificacion.ERROR_API,
    ),
    (
        "busy",
        cuerpo(409, '{"success":false,"error":"En curso","code":"BUSY"}'),
        Clasificacion.ERROR_API,
    ),
    (
        "insufficient_credit",
        cuerpo(422, '{"success":false,"error":"Sin crédito","code":"INSUFFICIENT_CREDIT"}'),
        Clasificacion.ERROR_API,
    ),
    (
        "invalid_key",
        cuerpo(401, '{"success":false,"error":"Key","code":"INVALID_KEY"}'),
        Clasificacion.ERROR_API,
    ),
    ("success_false_sin_code", cuerpo(500, '{"success":false}'), Clasificacion.ERROR_API),
    ("conexion_rechazada", httpx.ConnectError("rechazada"), Clasificacion.ERROR_PREVIO),
    ("timeout_conexion", httpx.ConnectTimeout("connect"), Clasificacion.ERROR_PREVIO),
    ("timeout_pool", httpx.PoolTimeout("pool"), Clasificacion.ERROR_PREVIO),
    ("timeout_lectura", httpx.ReadTimeout("read"), Clasificacion.INCIERTO),
    ("timeout_escritura", httpx.WriteTimeout("write"), Clasificacion.INCIERTO),
    ("corte_lectura", httpx.ReadError("reset"), Clasificacion.INCIERTO),
    ("protocolo", httpx.RemoteProtocolError("cortada"), Clasificacion.INCIERTO),
    ("html_502", cuerpo(502, "<html>502 Bad Gateway</html>"), Clasificacion.INCIERTO),
    ("cuerpo_vacio", cuerpo(200, ""), Clasificacion.INCIERTO),
    ("json_no_objeto", cuerpo(200, "[]"), Clasificacion.INCIERTO),
    ("sin_success", cuerpo(200, '{"data":{}}'), Clasificacion.INCIERTO),
    ("success_no_booleano", cuerpo(200, '{"success":"true","data":{}}'), Clasificacion.INCIERTO),
    ("sin_data", cuerpo(200, '{"success":true}'), Clasificacion.INCIERTO),
    (
        "sin_referencia",
        cuerpo(200, OK.replace('"referencia":"EV-9B5F34F9",', "")),
        Clasificacion.INCIERTO,
    ),
    ("monto_como_texto", cuerpo(200, OK.replace("0.50", '"0.50"')), Clasificacion.INCIERTO),
]


async def resultado_de_recarga(respuesta_o_error) -> object:
    with respx.mock(base_url=URL_BASE) as api:
        ruta = api.post("/recargar.php")
        if isinstance(respuesta_o_error, Exception):
            ruta.mock(side_effect=respuesta_o_error)
        else:
            ruta.mock(return_value=respuesta_o_error)
        async with ClienteVentasFF("rv_c_x") as cliente:
            try:
                return await cliente.recargar(1, "75807448")
            except ErrorVentasFF as error:
                return error


@pytest.mark.parametrize(
    ("respuesta", "esperada"), [c[1:] for c in CASOS], ids=[c[0] for c in CASOS]
)
async def test_clasificacion_de_recarga(respuesta, esperada):
    assert clasificar(await resultado_de_recarga(respuesta)) == esperada


async def test_success_false_sin_code_usa_desconocido():
    error = await resultado_de_recarga(cuerpo(500, '{"success":false}'))
    assert isinstance(error, ErrorAPI)
    assert (error.code, error.estado_http) == ("DESCONOCIDO", 500)


def test_valor_inesperado_es_incierto():
    assert clasificar(None) == Clasificacion.INCIERTO
    assert clasificar(ValueError("x")) == Clasificacion.INCIERTO
