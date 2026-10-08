import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.config import obtener_configuracion
from app.db import ErrorConexionBD, crear_fabrica_sesiones, crear_motor, verificar_conexion

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    config = obtener_configuracion()
    motor = crear_motor(config.database_url.get_secret_value())
    try:
        await verificar_conexion(motor)
    except Exception:
        await motor.dispose()
        raise
    app.state.motor = motor
    app.state.sesiones = crear_fabrica_sesiones(motor)
    yield
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
