"""Cliente de la API de VentasFF: único módulo que la llama (RNF-01; spec sec. 9).

La API Key solo viaja en la cabecera `Authorization` y nunca se registra
(RNF-05). Los montos se leen como `Decimal` directamente del JSON (RNF-04).
"""

import json
import logging
import time
from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum
from typing import Any, Self

import httpx

logger = logging.getLogger(__name__)

URL_BASE = "https://ventasff.com/api/reseller"
TIMEOUT_GENERAL = httpx.Timeout(30.0, connect=15.0)
TIMEOUT_RECARGA = httpx.Timeout(90.0, connect=15.0)


@dataclass(frozen=True)
class SaldoProveedor:
    credito: Decimal
    currency: str
    nombre: str


@dataclass(frozen=True)
class Producto:
    paquete_id: int
    nombre: str
    juego: str
    diamantes: int | None
    precio: Decimal  # precio de costo
    currency: str
    dato_extra: str | None


@dataclass(frozen=True)
class Validacion:
    valid: bool
    nickname: str | None
    estado: str  # ok | no_existe | no_disponible


@dataclass(frozen=True)
class RecargaRealizada:
    referencia: str
    monto: Decimal
    saldo: Decimal
    player_id: str
    nickname: str | None


class ErrorVentasFF(Exception):
    """Fallo al hablar con VentasFF."""


class ErrorAPI(ErrorVentasFF):
    """VentasFF respondió `success: false` con un código de error."""

    def __init__(self, code: str, mensaje: str, estado_http: int):
        super().__init__(f"{code}: {mensaje}")
        self.code = code
        self.mensaje = mensaje
        self.estado_http = estado_http


class ErrorPrevioAlEnvio(ErrorVentasFF):
    """La petición no llegó a enviarse (DNS, conexión rechazada, timeout de conexión).

    El proveedor no recibió nada: es seguro dar la recarga por fallida.
    """


class ResultadoIncierto(ErrorVentasFF):
    """La petición pudo procesarse pero no se sabe el resultado.

    Timeout o corte tras enviar, respuesta ilegible o fuera de contrato. Una
    recarga en este caso queda PENDIENTE_VERIFICAR y nunca se reintenta (RN-04).
    """


class Clasificacion(StrEnum):
    """Resultado de una llamada, según decide la Fase C (RF-24, plan 4.5)."""

    EXITO = "exito"
    ERROR_API = "error_api"
    ERROR_PREVIO = "error_previo"
    INCIERTO = "incierto"


# Fallos de transporte en los que la petición no salió del equipo.
_ERRORES_PREVIOS = (
    httpx.ConnectError,
    httpx.ConnectTimeout,
    httpx.PoolTimeout,
    httpx.UnsupportedProtocol,
)


def clasificar(resultado: object) -> Clasificacion:
    """Clasifica el valor devuelto o la excepción lanzada por el cliente."""
    match resultado:
        case ErrorAPI():
            return Clasificacion.ERROR_API
        case ErrorPrevioAlEnvio():
            return Clasificacion.ERROR_PREVIO
        case SaldoProveedor() | Validacion() | RecargaRealizada() | list():
            return Clasificacion.EXITO
        case _:
            # Cualquier otra cosa (incluido ResultadoIncierto) no permite saber si se cobró.
            return Clasificacion.INCIERTO


def _texto(datos: dict, campo: str, *, nulo: bool = False) -> str | None:
    valor = datos.get(campo)
    if valor is None and nulo:
        return None
    if not isinstance(valor, str):
        raise ResultadoIncierto(f"Campo {campo!r} ausente o no es texto")
    return valor


def _entero(datos: dict, campo: str, *, nulo: bool = False) -> int | None:
    valor = datos.get(campo)
    if valor is None and nulo:
        return None
    if isinstance(valor, bool) or not isinstance(valor, int):
        raise ResultadoIncierto(f"Campo {campo!r} ausente o no es entero")
    return valor


def _monto(datos: dict, campo: str) -> Decimal:
    valor = datos.get(campo)
    if isinstance(valor, bool) or not isinstance(valor, Decimal | int):
        raise ResultadoIncierto(f"Campo {campo!r} ausente o no es numérico")
    return Decimal(valor)


def _diccionario(data: Any) -> dict:
    if not isinstance(data, dict):
        raise ResultadoIncierto("`data` no es un objeto")
    return data


class ClienteVentasFF:
    def __init__(
        self,
        api_key: str,
        base_url: str = URL_BASE,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ):
        self._http = httpx.AsyncClient(
            base_url=base_url.rstrip("/") + "/",
            headers={"Authorization": f"Bearer {api_key}", "Accept": "application/json"},
            timeout=TIMEOUT_GENERAL,
            transport=transport,
        )

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *_) -> None:
        await self.cerrar()

    async def cerrar(self) -> None:
        await self._http.aclose()

    async def _peticion(
        self,
        metodo: str,
        ruta: str,
        *,
        params: dict | None = None,
        cuerpo: dict | None = None,
        timeout: httpx.Timeout = TIMEOUT_GENERAL,
    ) -> Any:
        """Devuelve `data` de una respuesta `success: true`."""
        inicio = time.monotonic()
        try:
            respuesta = await self._http.request(
                metodo, ruta, params=params, json=cuerpo, timeout=timeout
            )
        except httpx.HTTPError as error:
            previo = isinstance(error, _ERRORES_PREVIOS)
            logger.warning(
                "VentasFF %s %s falló %s del envío: %s (%.2fs)",
                metodo,
                ruta,
                "antes" if previo else "después",
                type(error).__name__,
                time.monotonic() - inicio,
            )
            if previo:
                raise ErrorPrevioAlEnvio(f"No se pudo enviar: {type(error).__name__}") from error
            raise ResultadoIncierto(f"Sin respuesta tras enviar: {type(error).__name__}") from error
        logger.info(
            "VentasFF %s %s -> %s (%.2fs)",
            metodo,
            ruta,
            respuesta.status_code,
            time.monotonic() - inicio,
        )

        try:
            cuerpo_json = json.loads(respuesta.content, parse_float=Decimal)
        except ValueError as error:
            raise ResultadoIncierto(f"Respuesta ilegible (HTTP {respuesta.status_code})") from error
        if not isinstance(cuerpo_json, dict) or not isinstance(cuerpo_json.get("success"), bool):
            raise ResultadoIncierto(f"Respuesta sin `success` (HTTP {respuesta.status_code})")

        if not cuerpo_json["success"]:
            code = cuerpo_json.get("code")
            mensaje = cuerpo_json.get("error")
            raise ErrorAPI(
                code if isinstance(code, str) and code else "DESCONOCIDO",
                mensaje if isinstance(mensaje, str) else "",
                respuesta.status_code,
            )
        return cuerpo_json.get("data")

    async def saldo(self) -> SaldoProveedor:
        data = _diccionario(await self._peticion("GET", "saldo.php"))
        return SaldoProveedor(
            credito=_monto(data, "credito"),
            currency=_texto(data, "currency"),
            nombre=_texto(data, "nombre"),
        )

    async def productos(self) -> list[Producto]:
        data = await self._peticion("GET", "productos.php")
        if not isinstance(data, list):
            raise ResultadoIncierto("`data` de productos no es una lista")
        productos = []
        for item in data:
            item = _diccionario(item)
            productos.append(
                Producto(
                    paquete_id=_entero(item, "paquete_id"),
                    nombre=_texto(item, "nombre"),
                    juego=_texto(item, "juego"),
                    diamantes=_entero(item, "diamantes", nulo=True),
                    precio=_monto(item, "precio"),
                    currency=_texto(item, "currency"),
                    dato_extra=_texto(item, "dato_extra", nulo=True),
                )
            )
        return productos

    async def validar(self, player_id: str, paquete_id: int) -> Validacion:
        data = _diccionario(
            await self._peticion(
                "GET", "validar.php", params={"player_id": player_id, "paquete_id": paquete_id}
            )
        )
        valid = data.get("valid")
        if not isinstance(valid, bool):
            raise ResultadoIncierto("Campo 'valid' ausente o no es booleano")
        return Validacion(
            valid=valid,
            nickname=_texto(data, "nickname", nulo=True),
            estado=_texto(data, "estado"),
        )

    async def recargar(self, paquete_id: int, player_id: str) -> RecargaRealizada:
        data = _diccionario(
            await self._peticion(
                "POST",
                "recargar.php",
                cuerpo={"paquete_id": paquete_id, "player_id": player_id},
                timeout=TIMEOUT_RECARGA,
            )
        )
        return RecargaRealizada(
            referencia=_texto(data, "referencia"),
            monto=_monto(data, "monto"),
            saldo=_monto(data, "saldo"),
            player_id=_texto(data, "player_id"),
            nickname=_texto(data, "nickname", nulo=True),
        )
