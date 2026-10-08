"""Fixtures de base de datos: esquema `test` aislado (RNF-10).

El esquema se crea al inicio de la sesión de pytest, se migra con Alembic y se
elimina al final. Ninguna fixture toca otro esquema.
"""

from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text

from app.config import obtener_configuracion
from app.db import crear_fabrica_sesiones, crear_motor

ESQUEMA_TEST = "test"
RAIZ = Path(__file__).resolve().parent.parent


def _url_test() -> str:
    url = obtener_configuracion().test_database_url
    if url is None or not url.get_secret_value():
        pytest.fail(
            "TEST_DATABASE_URL es obligatoria para las pruebas de base de datos (ver .env.example)"
        )
    return url.get_secret_value()


def _recrear_esquema(url: str, crear: bool) -> None:
    assert ESQUEMA_TEST == "test"  # salvaguarda: nunca borrar otro esquema
    motor = create_engine(url)
    with motor.begin() as conexion:
        conexion.execute(text(f'DROP SCHEMA IF EXISTS "{ESQUEMA_TEST}" CASCADE'))
        if crear:
            conexion.execute(text(f'CREATE SCHEMA "{ESQUEMA_TEST}"'))
    motor.dispose()


def _migrar(url: str) -> None:
    # Config sin archivo: no reconfigura el logging de pytest.
    config = Config()
    config.set_main_option("script_location", str(RAIZ / "migrations"))
    config.attributes["url"] = url
    config.attributes["esquema"] = ESQUEMA_TEST
    command.upgrade(config, "head")


@pytest.fixture(scope="session")
def url_bd_test() -> str:
    """URL de pruebas con el esquema `test` recién creado y migrado."""
    url = _url_test()
    _recrear_esquema(url, crear=True)
    _migrar(url)
    yield url
    _recrear_esquema(url, crear=False)


@pytest.fixture
async def motor_bd(url_bd_test):
    motor = crear_motor(url_bd_test, esquema=ESQUEMA_TEST)
    yield motor
    await motor.dispose()


@pytest.fixture
async def sesion_bd(motor_bd):
    async with crear_fabrica_sesiones(motor_bd)() as sesion:
        yield sesion
