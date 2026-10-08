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


@pytest.fixture(scope="session")
async def motor_bd(url_bd_test):
    """Un motor para toda la sesión: cada conexión nueva al VPS es costosa."""
    motor = crear_motor(url_bd_test, esquema=ESQUEMA_TEST)
    yield motor
    await motor.dispose()


@pytest.fixture
async def sesion_bd(motor_bd):
    async with crear_fabrica_sesiones(motor_bd)() as sesion:
        yield sesion


@pytest.fixture
async def cuenta(sesion_bd):
    """Id de un cliente nuevo con saldo en cero, ya confirmado en la BD."""
    from app.services import ledger
    from tests.utilidades import crear_usuario

    usuario = await crear_usuario(sesion_bd)
    await ledger.abrir_cuenta(sesion_bd, usuario.id)
    await sesion_bd.commit()
    return usuario.id


@pytest.fixture
async def admin_id(sesion_bd):
    from tests.utilidades import crear_usuario

    usuario = await crear_usuario(sesion_bd, rol="admin")
    await sesion_bd.commit()
    return usuario.id


@pytest.fixture
def simulador():
    """Simulador de VentasFF que usa la app en las pruebas de la API (RNF-08)."""
    from tests.fake_ventasff import SimuladorVentasFF

    return SimuladorVentasFF()


@pytest.fixture
async def api(motor_bd, simulador):
    """Fábrica de clientes HTTP contra la app, con la BD del esquema `test`.

    Cada cliente tiene su propio tarro de cookies (una sesión por cliente). El
    limitador de login es nuevo en cada prueba. `ip` fija la IP del cliente.
    VentasFF es el `simulador` de la prueba.
    """
    import httpx

    from app.main import app
    from app.services.limitador import LimitadorTasa
    from app.services.limitador_login import LimitadorLogin
    from app.services.ventasff_client import ClienteVentasFF

    app.state.motor = motor_bd
    app.state.sesiones = crear_fabrica_sesiones(motor_bd)
    app.state.cookie_secure = False
    app.state.limitador_login = LimitadorLogin()
    app.state.ventasff = ClienteVentasFF(
        simulador.api_key, "http://simulador/api/reseller", transport=simulador.transporte()
    )
    app.state.limitador_recargas = LimitadorTasa(1000)
    app.state.crear_cliente_ventasff = lambda: ClienteVentasFF(
        simulador.api_key, "http://simulador/api/reseller", transport=simulador.transporte()
    )
    app.state.tareas_recarga = set()
    clientes = []

    def nuevo(ip: str = "127.0.0.1") -> httpx.AsyncClient:
        transporte = httpx.ASGITransport(app=app, client=(ip, 50000))
        cliente = httpx.AsyncClient(transport=transporte, base_url="http://test")
        clientes.append(cliente)
        return cliente

    yield nuevo
    for cliente in clientes:
        await cliente.aclose()
    await app.state.ventasff.cerrar()
