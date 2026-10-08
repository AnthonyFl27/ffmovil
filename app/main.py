import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.config import obtener_configuracion
from app.db import ErrorConexionBD, crear_fabrica_sesiones, crear_motor, verificar_conexion
from app.logs import configurar_logs
from app.services.recuperacion import recuperar_pedidos_huerfanos
from app.services.tareas import crear_programador
from app.services.ventasff_client import ClienteVentasFF

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    config = obtener_configuracion()
    configurar_logs(config)
    motor = crear_motor(config.database_url.get_secret_value())
    try:
        await verificar_conexion(motor)
    except Exception:
        await motor.dispose()
        raise
    app.state.motor = motor
    app.state.sesiones = crear_fabrica_sesiones(motor)
    # RN-09: pedidos que quedaron en PROCESANDO por un reinicio pasan a revisión.
    async with app.state.sesiones() as sesion:
        await recuperar_pedidos_huerfanos(sesion)

    def crear_cliente() -> ClienteVentasFF:
        return ClienteVentasFF(config.ventasff_api_key.get_secret_value(), config.ventasff_url)

    # Sincronización diaria del catálogo (RF-10); la app corre con un solo worker.
    programador = crear_programador(app.state.sesiones, crear_cliente)
    programador.start()
    yield
    programador.shutdown(wait=False)
    await motor.dispose()


app = FastAPI(title="ffmovil", lifespan=lifespan)


@app.get("/health")
async def health(request: Request):
    try:
        await verificar_conexion(request.app.state.motor)
    except ErrorConexionBD as error:
        # El motivo va al log del servidor (sin contraseña), no a la respuesta.
        logger.warning("health: %s", error)
        return JSONResponse({"estado": "error", "bd": "error"}, status_code=503)
    return {"estado": "ok", "bd": "ok"}
