import httpx
import pytest

from app.config import obtener_configuracion
from app.db import crear_motor
from app.main import app

URL_INACCESIBLE = "postgresql+psycopg://usuario:clave@127.0.0.1:1/bd"


@pytest.fixture
async def cliente_con_motor():
    motores = []

    async def crear(url: str) -> httpx.AsyncClient:
        motor = crear_motor(url)
        motores.append(motor)
        app.state.motor = motor
        return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")

    yield crear
    for motor in motores:
        await motor.dispose()


async def test_health_ok(cliente_con_motor):
    url = obtener_configuracion().test_database_url
    assert url, "TEST_DATABASE_URL es obligatoria para las pruebas"
    async with await cliente_con_motor(url.get_secret_value()) as cliente:
        respuesta = await cliente.get("/health")
    assert respuesta.status_code == 200
    assert respuesta.json() == {"estado": "ok", "bd": "ok"}


async def test_health_sin_bd_responde_503_sin_detalles(cliente_con_motor):
    async with await cliente_con_motor(URL_INACCESIBLE) as cliente:
        respuesta = await cliente.get("/health")
    assert respuesta.status_code == 503
    assert respuesta.json() == {"estado": "error", "bd": "error"}
