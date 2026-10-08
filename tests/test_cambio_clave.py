"""T-051: cambio obligatorio de contraseña y acceso restringido (RF-02, RF-06, RF-08)."""

import httpx
import pytest
from fastapi import FastAPI

from app.routers.dependencias import Actual, Admin
from app.services import auth_service
from tests.utilidades_api import CLAVE, crear_usuario_con_clave, iniciar_sesion

NUEVA = "otra-clave-segura"

# App mínima con rutas protegidas por las dependencias reales.
app_prueba = FastAPI()


@app_prueba.get("/protegida")
async def protegida(actual: Actual):
    return {"usuario": actual.usuario.usuario}


@app_prueba.get("/solo-admin")
async def solo_admin(actual: Admin):
    return {"ok": True}


def cliente_prueba(cliente_api: httpx.AsyncClient) -> httpx.AsyncClient:
    """Cliente contra `app_prueba` con las cookies y la BD del cliente de la app real."""
    from app.main import app

    app_prueba.state.sesiones = app.state.sesiones
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app_prueba),
        base_url="http://test",
        cookies=cliente_api.cookies,
    )


async def test_debe_cambiar_clave_solo_accede_al_cambio(api, sesion_bd):
    usuario = await crear_usuario_con_clave(sesion_bd, debe_cambiar_clave=True)
    c = api()
    login = await iniciar_sesion(c, usuario.usuario)
    assert login.json()["debe_cambiar_clave"] is True
    async with cliente_prueba(c) as p:
        bloqueada = await p.get("/protegida")
    assert bloqueada.status_code == 403
    assert "cambiar tu contraseña" in bloqueada.json()["detail"]
    # /auth/sesion sigue disponible para saber que debe cambiarla.
    assert (await c.get("/auth/sesion")).status_code == 200

    cambio = await c.post("/auth/cambiar-clave", json={"clave_actual": CLAVE, "clave_nueva": NUEVA})
    assert cambio.status_code == 200
    assert cambio.json()["debe_cambiar_clave"] is False
    c.headers["X-CSRF-Token"] = cambio.json()["csrf"]
    async with cliente_prueba(c) as p:
        assert (await p.get("/protegida")).status_code == 200
        # Un cliente no entra a rutas de admin.
        assert (await p.get("/solo-admin")).status_code == 403

    await sesion_bd.refresh(usuario)
    assert auth_service.verificar_clave(usuario.hash_password, NUEVA)
    assert (await iniciar_sesion(api(), usuario.usuario, NUEVA)).status_code == 200
    assert (await iniciar_sesion(api(), usuario.usuario, CLAVE)).status_code == 401


async def test_cambio_cierra_las_demas_sesiones(api, sesion_bd):
    usuario = await crear_usuario_con_clave(sesion_bd)
    otra, propia = api(), api()
    await iniciar_sesion(otra, usuario.usuario)
    await iniciar_sesion(propia, usuario.usuario)
    token_anterior = propia.cookies["sesion"]

    cambio = await propia.post(
        "/auth/cambiar-clave", json={"clave_actual": CLAVE, "clave_nueva": NUEVA}
    )
    assert cambio.status_code == 200
    # Quien cambió la clave recibe una sesión nueva; las anteriores se cierran.
    assert propia.cookies["sesion"] != token_anterior
    assert (await propia.get("/auth/sesion")).status_code == 200
    assert (await otra.get("/auth/sesion")).status_code == 401


@pytest.mark.parametrize(
    ("actual", "nueva", "mensaje"),
    [
        ("incorrecta-1", NUEVA, "actual es incorrecta"),
        (CLAVE, "corta12", "de 8 a 128"),
        (CLAVE, "x" * 129, "de 8 a 128"),
        (CLAVE, CLAVE, "distinta de la actual"),
    ],
)
async def test_cambio_rechazado(api, sesion_bd, actual, nueva, mensaje):
    usuario = await crear_usuario_con_clave(sesion_bd, debe_cambiar_clave=True)
    c = api()
    await iniciar_sesion(c, usuario.usuario)
    respuesta = await c.post(
        "/auth/cambiar-clave", json={"clave_actual": actual, "clave_nueva": nueva}
    )
    assert respuesta.status_code == 400
    assert mensaje in respuesta.json()["detail"]
    assert (await c.get("/auth/sesion")).json()["debe_cambiar_clave"] is True


async def test_cambio_exige_csrf(api, sesion_bd):
    usuario = await crear_usuario_con_clave(sesion_bd)
    c = api()
    await iniciar_sesion(c, usuario.usuario)
    del c.headers["X-CSRF-Token"]
    respuesta = await c.post(
        "/auth/cambiar-clave", json={"clave_actual": CLAVE, "clave_nueva": NUEVA}
    )
    assert respuesta.status_code == 403
