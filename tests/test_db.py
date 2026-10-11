import pytest
from fastapi import FastAPI

from app.config import obtener_configuracion
from app.db import POOL_BASE, POOL_EXTRA, ErrorConexionBD, crear_motor, verificar_conexion
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


async def test_el_pool_deja_margen_bajo_el_limite_de_conexiones_del_rol():
    """RNF-07: la app usa a lo sumo 8 conexiones; el rol de producción admite 15."""
    motor = crear_motor(URL_INACCESIBLE)
    try:
        assert motor.sync_engine.pool.size() == POOL_BASE
        assert motor.sync_engine.pool._max_overflow == POOL_EXTRA
        assert POOL_BASE + POOL_EXTRA <= 8
    finally:
        await motor.dispose()
