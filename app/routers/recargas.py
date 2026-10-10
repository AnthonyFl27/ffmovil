"""Validación del Player ID y creación de recargas (RF-20 a RF-27, plan 4.1 y 4.2).

`POST /recargas` ejecuta la Fase A en la petición. Las fases B y C corren en una
tarea propia que no se cancela si el cliente se desconecta (plan 4.6); la ruta
espera su resultado un tiempo acotado y, si no termina, devuelve el pedido en
proceso para consultarlo luego en `/me/pedidos/{codigo}`.
"""

import asyncio
import logging

from fastapi import APIRouter, FastAPI, HTTPException, Request, Response, status

from app.models import Pedido
from app.routers.dependencias import Bd, Cliente
from app.routers.me import consulta_pedidos_cliente, pedido_cliente
from app.schemas.cliente import (
    PedidoCliente,
    SolicitudRecarga,
    SolicitudValidacion,
    ValidacionJugador,
)
from app.services import recarga_service
from app.services.ledger import SaldoInsuficiente
from app.services.recarga_service import ConfirmacionRequerida, ErrorRecarga

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/recargas", tags=["cliente"])

# Espera máxima del resultado del proveedor dentro de la petición.
ESPERA_RESULTADO_SEGUNDOS = 20.0
MENSAJE_SALDO_INSUFICIENTE = "Saldo insuficiente para esta recarga."
MENSAJE_DEMASIADAS_VALIDACIONES = (
    "Demasiadas verificaciones. Espera un momento e inténtalo de nuevo."
)


@router.post("/validar", response_model=ValidacionJugador)
async def validar(datos: SolicitudValidacion, request: Request, actual: Cliente, bd: Bd):
    """Valida el Player ID y devuelve el nickname (RF-20, RF-27); `no_existe` → 422.

    Tope de 10 por minuto y usuario (RF-56): superado, 429 sin llamar a VentasFF.
    """
    if not request.app.state.limitador_validaciones.intentar(actual.usuario_id):
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, MENSAJE_DEMASIADAS_VALIDACIONES)
    try:
        resultado = await recarga_service.validar_jugador(
            bd, request.app.state.ventasff, datos.player_id, datos.paquete_id
        )
    except ErrorRecarga as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(error)) from None
    return ValidacionJugador(
        estado=resultado.estado, nickname=resultado.nickname, advertencia=resultado.advertencia
    )


def lanzar_procesamiento(app: FastAPI, pedido_id: int) -> asyncio.Task:
    """Fases B y C en una tarea guardada en `app.state` (no se cancela con la petición)."""
    tarea = asyncio.create_task(
        recarga_service.procesar_pedido(
            app.state.sesiones,
            app.state.motor,
            app.state.ventasff,
            app.state.limitador_recargas,
            pedido_id,
        ),
        name=f"recarga-{pedido_id}",
    )
    app.state.tareas_recarga.add(tarea)

    def al_terminar(t: asyncio.Task) -> None:
        app.state.tareas_recarga.discard(t)
        if not t.cancelled() and t.exception() is not None:
            # El pedido queda en PROCESANDO; al reiniciar pasa a revisión (RN-09).
            logger.error("Falló el procesamiento del pedido %s", pedido_id, exc_info=t.exception())

    tarea.add_done_callback(al_terminar)
    return tarea


@router.post("", response_model=PedidoCliente)
async def crear_recarga(
    datos: SolicitudRecarga, request: Request, response: Response, actual: Cliente, bd: Bd
):
    """Crea la recarga (RF-21 a RF-25). 201 si es nueva; 200 si el token ya se usó (CA-02)."""
    app = request.app
    try:
        creado = await recarga_service.crear_pedido(
            bd,
            app.state.ventasff,
            actual.usuario_id,
            datos.paquete_id,
            datos.player_id,
            datos.token_idempotencia,
            confirmar_sin_verificar=datos.confirmar_sin_verificar,
        )
    except ConfirmacionRequerida as error:
        raise HTTPException(status.HTTP_409_CONFLICT, error.advertencia) from None
    except ErrorRecarga as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(error)) from None
    except SaldoInsuficiente:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, MENSAJE_SALDO_INSUFICIENTE
        ) from None

    pedido_id = creado.pedido.id
    if creado.nuevo:
        response.status_code = status.HTTP_201_CREATED
        tarea = lanzar_procesamiento(app, pedido_id)
        # asyncio.wait no cancela la tarea si vence el plazo o se cancela la petición.
        await asyncio.wait({tarea}, timeout=ESPERA_RESULTADO_SEGUNDOS)

    consulta = consulta_pedidos_cliente(actual.usuario_id).where(Pedido.id == pedido_id)
    fila = (await bd.execute(consulta.execution_options(populate_existing=True))).one()
    return pedido_cliente(*fila)
