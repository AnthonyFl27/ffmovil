from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.config import obtener_configuracion
from app.db import crear_fabrica_sesiones, crear_motor, verificar_conexion


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
