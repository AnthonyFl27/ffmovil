import pytest
from fastapi import FastAPI

from app.config import obtener_configuracion
from app.db import ErrorConexionBD, crear_motor, verificar_conexion
from app.main import lifespan

# Puerto 1 en localhost: nada escucha ahí, la conexión se rechaza sin red.
URL_INACCESIBLE = "postgresql+psycopg://usuario:clave-secreta-123@127.0.0.1:1/bd"


async def test_verificar_conexion_falla_con_error_claro():
    motor = crear_motor(URL_INACCESIBLE)
    with pytest.raises(ErrorConexionBD) as error:
        await verificar_conexion(motor)
    await motor.dispose()
    mensaje = str(error.value)
    assert "DATABASE_URL" in mensaje
    assert "127.0.0.1:1" in mensaje
    assert "clave-secreta-123" not in mensaje


async def test_app_no_arranca_si_la_bd_no_responde(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", URL_INACCESIBLE)
    obtener_configuracion.cache_clear()
    try:
        with pytest.raises(ErrorConexionBD):
            async with lifespan(FastAPI()):
                pass
    finally:
        obtener_configuracion.cache_clear()
