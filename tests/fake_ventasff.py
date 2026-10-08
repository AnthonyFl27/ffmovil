"""Simulador de la API de VentasFF para pruebas y desarrollo (RNF-08).

En pruebas se usa como transporte de ``httpx.AsyncClient``::

    sim = SimuladorVentasFF()
    cliente = httpx.AsyncClient(transport=sim.transporte(), base_url=...)

En desarrollo se levanta como servidor HTTP local::

    uv run python -m tests.fake_ventasff --port 8099

Nunca contacta a la API real. Los precios son ficticios.
"""

import argparse
import asyncio
import json
import uuid
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

import httpx
import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import Response

RUTA_BASE = "/api/reseller"
MONEDA = "USD"
ESCENARIOS_RECARGA = (
    "ok",
    "nickname_null",
    "PURCHASE_FAILED",
    "BUSY",
    "INSUFFICIENT_CREDIT",
    "INVALID_KEY",
    "RATE_LIMITED",
    "timeout",
    "ilegible",
    "error_conexion",
)
# Escenarios que cobran el paquete (el proveedor procesó la recarga).
_ESCENARIOS_CON_COBRO = ("ok", "nickname_null", "timeout", "ilegible")
_SEGUNDOS_TIMEOUT_SERVIDOR = 120


def productos_de_ejemplo() -> list[dict[str, Any]]:
    """Catálogo ficticio de VentasFF (sin precios reales: el repositorio es público)."""
    return [
        {
            "paquete_id": 1,
            "nombre": "110 Diamantes",
            "juego": "free_fire",
            "diamantes": 110,
            "precio": Decimal("0.50"),
            "currency": MONEDA,
            "dato_extra": None,
        },
        {
            "paquete_id": 2,
            "nombre": "341 Diamantes",
            "juego": "free_fire",
            "diamantes": 341,
            "precio": Decimal("2.40"),
            "currency": MONEDA,
            "dato_extra": None,
        },
        {
            "paquete_id": 3,
            "nombre": "572 Diamantes",
            "juego": "free_fire",
            "diamantes": 572,
            "precio": Decimal("4.00"),
            "currency": MONEDA,
            "dato_extra": None,
        },
        {
            "paquete_id": 193,
            "nombre": "86 Diamantes",
            "juego": "mobile_legends",
            "diamantes": 86,
            "precio": Decimal("1.10"),
            "currency": MONEDA,
            "dato_extra": "Zone ID",
        },
    ]


def _a_json(valor: Any) -> str:
    """Serializa a JSON escribiendo los Decimal como número exacto (sin pasar por float)."""

    def convertir(v: Any) -> str:
        if isinstance(v, Decimal):
            return format(v, "f")
        if isinstance(v, dict):
            pares = ",".join(f"{json.dumps(str(k))}:{convertir(x)}" for k, x in v.items())
            return "{" + pares + "}"
        if isinstance(v, list):
            return "[" + ",".join(convertir(x) for x in v) + "]"
        if v is None or isinstance(v, str | bool | int):
            return json.dumps(v, ensure_ascii=False)
        raise TypeError(f"Tipo no serializable en el simulador: {type(v).__name__}")

    return convertir(valor)


@dataclass
class RespuestaSimulada:
    """Respuesta ya decidida. `cobrado` indica que se descontó crédito."""

    status: int
    cuerpo: str
    cabeceras: dict[str, str] = field(default_factory=dict)
    tipo: str = "application/json"
    cobrado: bool = False


def _error(
    status: int, codigo: str, mensaje: str, cabeceras: dict[str, str] | None = None
) -> RespuestaSimulada:
    cuerpo = _a_json({"success": False, "error": mensaje, "code": codigo})
    return RespuestaSimulada(status, cuerpo, cabeceras or {})


def _exito(datos: Any) -> RespuestaSimulada:
    return RespuestaSimulada(200, _a_json({"success": True, "data": datos}))


def _leer_cuerpo(cuerpo: bytes) -> dict[str, Any]:
    """Lee el cuerpo JSON de recargar.php; si no es un objeto válido devuelve vacío."""
    try:
        datos = json.loads(cuerpo)
    except ValueError:
        return {}
    return datos if isinstance(datos, dict) else {}


def _vacio(valor: Any) -> bool:
    return valor is None or valor == ""


def _como_response(respuesta: RespuestaSimulada) -> Response:
    return Response(
        content=respuesta.cuerpo,
        status_code=respuesta.status,
        headers=respuesta.cabeceras,
        media_type=respuesta.tipo,
    )


@dataclass
class SimuladorVentasFF:
    """Simulador de VentasFF con escenarios configurables.

    `busy_restantes`: mientras sea mayor que 0, recargar.php responde BUSY y decrementa.
    `peticiones`: (método, ruta) de cada petición recibida.
    `recargas`: recargas efectivamente procesadas (con crédito descontado).
    """

    api_key: str = "rv_c_simulador"
    credito: Decimal = Decimal("100.00")
    productos: list[dict[str, Any]] = field(default_factory=productos_de_ejemplo)
    escenario_recarga: str = "ok"
    escenario_validar: str = "ok"  # "ok" | "no_existe" | "no_disponible"
    busy_restantes: int = 0
    retry_after: int = 2
    peticiones: list[tuple[str, str]] = field(default_factory=list)
    recargas: list[dict[str, Any]] = field(default_factory=list)

    def app(self) -> FastAPI:
        """Aplicación ASGI con los cuatro endpoints de la sección 9 de la spec."""
        api = FastAPI()

        @api.get(f"{RUTA_BASE}/saldo.php")
        async def saldo(request: Request) -> Response:
            self._registrar(request)
            return _como_response(self._saldo(request.headers.get("authorization")))

        @api.get(f"{RUTA_BASE}/productos.php")
        async def productos(request: Request) -> Response:
            self._registrar(request)
            return _como_response(self._productos(request.headers.get("authorization")))

        @api.get(f"{RUTA_BASE}/validar.php")
        async def validar(request: Request) -> Response:
            self._registrar(request)
            respuesta = self._validar(request.headers.get("authorization"), request.query_params)
            return _como_response(respuesta)

        @api.post(f"{RUTA_BASE}/recargar.php")
        async def recargar(request: Request) -> Response:
            self._registrar(request)
            respuesta = self._recargar(request.headers.get("authorization"), await request.body())
            if respuesta.cobrado and self.escenario_recarga == "timeout":
                # En servidor, el "timeout" cobra y luego tarda en responder.
                await asyncio.sleep(_SEGUNDOS_TIMEOUT_SERVIDOR)
            return _como_response(respuesta)

        return api

    def transporte(self) -> httpx.AsyncBaseTransport:
        """Transporte para ``httpx.AsyncClient(transport=...)``."""
        return TransporteSimulado(self)

    # Lógica de respuesta por endpoint.

    def _registrar(self, request: Request) -> None:
        self.peticiones.append((request.method, request.url.path))

    def _error_clave(self, cabecera: str | None) -> RespuestaSimulada | None:
        if cabecera is None:
            return _error(401, "MISSING_KEY", "Falta la cabecera Authorization")
        if cabecera != f"Bearer {self.api_key}":
            return _error(401, "INVALID_KEY", "API Key inválida")
        return None

    def _saldo(self, cabecera: str | None) -> RespuestaSimulada:
        if error := self._error_clave(cabecera):
            return error
        datos = {"credito": self.credito, "currency": MONEDA, "nombre": "Simulador"}
        return _exito(datos)

    def _productos(self, cabecera: str | None) -> RespuestaSimulada:
        if error := self._error_clave(cabecera):
            return error
        return _exito(self.productos)

    def _validar(self, cabecera: str | None, parametros: Any) -> RespuestaSimulada:
        if error := self._error_clave(cabecera):
            return error
        faltan = [n for n in ("player_id", "paquete_id") if _vacio(parametros.get(n))]
        if faltan:
            mensaje = f"Faltan campos: {' y '.join(faltan)}"
            return _error(422, "MISSING_FIELD", mensaje)
        if self.escenario_validar == "no_existe":
            datos = {"valid": False, "nickname": None, "estado": "no_existe"}
        elif self.escenario_validar == "no_disponible":
            datos = {"valid": False, "nickname": None, "estado": "no_disponible"}
        else:
            nickname = f"Jugador{parametros['player_id'][-4:]}"
            datos = {"valid": True, "nickname": nickname, "estado": "ok"}
        return _exito(datos)

    def _recargar(self, cabecera: str | None, cuerpo: bytes) -> RespuestaSimulada:
        """Procesa recargar.php. Es el único punto donde se descuenta crédito."""
        if error := self._error_clave(cabecera):
            return error
        datos = _leer_cuerpo(cuerpo)
        paquete_id = datos.get("paquete_id")
        player_id = datos.get("player_id")
        if _vacio(paquete_id) or _vacio(player_id):
            return _error(422, "MISSING_FIELD", "Faltan campos: paquete_id y player_id")
        paquete = next((p for p in self.productos if p["paquete_id"] == paquete_id), None)
        if paquete is None:
            return _error(422, "PURCHASE_FAILED", "Paquete no disponible")
        if self.busy_restantes > 0:
            self.busy_restantes -= 1
            return _error(409, "BUSY", "Otra recarga en curso")

        escenario = self.escenario_recarga
        if escenario == "PURCHASE_FAILED":
            return _error(422, "PURCHASE_FAILED", "Paquete no disponible")
        if escenario == "BUSY":
            return _error(409, "BUSY", "Otra recarga en curso")
        if escenario == "INSUFFICIENT_CREDIT":
            return _error(422, "INSUFFICIENT_CREDIT", "Crédito insuficiente")
        if escenario == "INVALID_KEY":
            return _error(401, "INVALID_KEY", "API Key inválida")
        if escenario == "RATE_LIMITED":
            cabeceras = {"Retry-After": str(self.retry_after)}
            return _error(429, "RATE_LIMITED", "Demasiadas peticiones", cabeceras)
        if escenario == "error_conexion":
            return RespuestaSimulada(503, "")

        # ok, nickname_null, timeout e ilegible: el proveedor cobra.
        if self.credito < paquete["precio"]:
            return _error(422, "INSUFFICIENT_CREDIT", "Crédito insuficiente")
        data = self._cobrar(paquete, player_id, con_nickname=escenario != "nickname_null")
        if escenario == "ilegible":
            return RespuestaSimulada(
                200, "<html>502 Bad Gateway</html>", tipo="text/html", cobrado=True
            )
        return RespuestaSimulada(200, _a_json({"success": True, "data": data}), cobrado=True)

    def _cobrar(
        self, paquete: dict[str, Any], player_id: Any, con_nickname: bool
    ) -> dict[str, Any]:
        precio: Decimal = paquete["precio"]
        self.credito -= precio
        referencia = self._nueva_referencia()
        self.recargas.append(
            {
                "referencia": referencia,
                "paquete_id": paquete["paquete_id"],
                "player_id": player_id,
                "monto": precio,
            }
        )
        nickname = f"Jugador{str(player_id)[-4:]}" if con_nickname else None
        return {
            "referencia": referencia,
            "monto": precio,
            "saldo": self.credito,
            "player_id": player_id,
            "nickname": nickname,
        }

    def _nueva_referencia(self) -> str:
        usadas = {r["referencia"] for r in self.recargas}
        while True:
            referencia = f"EV-{uuid.uuid4().hex[:8].upper()}"
            if referencia not in usadas:
                return referencia


class TransporteSimulado(httpx.AsyncBaseTransport):
    """Transporte httpx que sirve el simulador en memoria, sin red.

    Los escenarios "error_conexion" y "timeout" se resuelven aquí porque son
    fallos de transporte: no existe una respuesta HTTP que devolver.
    """

    def __init__(self, simulador: SimuladorVentasFF) -> None:
        self._simulador = simulador
        self._asgi = httpx.ASGITransport(app=simulador.app())

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        sim = self._simulador
        es_recargar = request.method == "POST" and request.url.path.endswith("/recargar.php")
        if es_recargar and sim.escenario_recarga == "error_conexion":
            sim.peticiones.append((request.method, request.url.path))
            raise httpx.ConnectError("conexión rechazada", request=request)
        if es_recargar and sim.escenario_recarga == "timeout" and sim.busy_restantes == 0:
            sim.peticiones.append((request.method, request.url.path))
            await request.aread()
            respuesta = sim._recargar(request.headers.get("authorization"), request.content)
            if respuesta.cobrado:
                raise httpx.ReadTimeout("tiempo agotado", request=request)
            cabeceras = {**respuesta.cabeceras, "content-type": respuesta.tipo}
            return httpx.Response(
                respuesta.status,
                headers=cabeceras,
                content=respuesta.cuerpo.encode(),
                request=request,
            )
        return await self._asgi.handle_async_request(request)


def main() -> None:
    parser = argparse.ArgumentParser(description="Simulador local de la API de VentasFF")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8099)
    parser.add_argument("--escenario", default="ok", choices=ESCENARIOS_RECARGA)
    parser.add_argument("--api-key", default="rv_c_simulador")
    args = parser.parse_args()
    sim = SimuladorVentasFF(api_key=args.api_key, escenario_recarga=args.escenario)
    uvicorn.run(sim.app(), host=args.host, port=args.port)


if __name__ == "__main__":
    main()
