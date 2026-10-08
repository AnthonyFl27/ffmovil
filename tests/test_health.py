import httpx

from app.db import crear_motor
from app.main import app

URL_INACCESIBLE = "postgresql+psycopg://usuario:clave@127.0.0.1:1/bd"


def cliente(motor) -> httpx.AsyncClient:
    app.state.motor = motor
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


async def test_health_ok(motor_bd):
    async with cliente(motor_bd) as c:
        respuesta = await c.get("/health")
    assert respuesta.status_code == 200
    assert respuesta.json() == {"estado": "ok", "bd": "ok"}


async def test_health_sin_bd_responde_503_sin_detalles():
    motor = crear_motor(URL_INACCESIBLE)
    async with cliente(motor) as c:
        respuesta = await c.get("/health")
    await motor.dispose()
    assert respuesta.status_code == 503
    assert respuesta.json() == {"estado": "error", "bd": "error"}
