"""T-111 a T-114: cabeceras, documentación, IP tras proxy y límite de validación.

RNF-14, RNF-15, RNF-16, RF-56 (CHG-017).
"""

from types import SimpleNamespace

import pytest
from starlette.requests import Request

from app.cabeceras import CSP
from app.main import app
from app.routers.dependencias import ip_cliente
from app.services.limitador import LimitadorPorUsuario
from tests.utilidades_api import CLAVE, crear_usuario_con_clave, iniciar_sesion
from tests.utilidades_web import cliente_web, htmx_post

CABECERAS_ESPERADAS = {
    "x-content-type-options": "nosniff",
    "x-frame-options": "DENY",
    "referrer-policy": "same-origin",
    "content-security-policy": CSP,
}


def _con_cabeceras(respuesta, *, no_store: bool = True) -> None:
    for nombre, valor in CABECERAS_ESPERADAS.items():
        assert respuesta.headers.get(nombre) == valor, nombre
    if no_store:
        assert respuesta.headers.get("cache-control") == "no-store"


def test_la_csp_no_permite_nada_en_linea():
    assert "unsafe-inline" not in CSP and "unsafe-eval" not in CSP
    assert "frame-ancestors 'none'" in CSP and "default-src 'self'" in CSP


# --- T-111: cabeceras --------------------------------------------------------------


async def test_cabeceras_en_paginas_api_y_errores(api, sesion_bd):
    http = api()
    _con_cabeceras(await http.get("/login"))
    _con_cabeceras(await http.get("/health"))
    _con_cabeceras(await http.get("/auth/sesion"))  # 401
    _con_cabeceras(await http.get("/inicio", follow_redirects=False))  # 303 a /login
    _con_cabeceras(await http.post("/auth/login", content=b"x" * 70_000))  # 413
    usuario = await crear_usuario_con_clave(sesion_bd, "cliente")
    await iniciar_sesion(http, usuario.usuario)
    for ruta in ("/inicio", "/recargar", "/historial", "/fondos", "/me/resumen"):
        _con_cabeceras(await http.get(ruta))


async def test_los_estaticos_llevan_cabeceras_pero_conservan_su_cache(api):
    r = await api().get("/static/app.css")
    assert r.status_code == 200
    _con_cabeceras(r, no_store=False)
    assert r.headers.get("cache-control") != "no-store"


# --- T-112: documentación ----------------------------------------------------------


@pytest.mark.parametrize("ruta", ["/docs", "/redoc", "/openapi.json", "/docs/oauth2-redirect"])
async def test_no_hay_documentacion_publica(api, ruta):
    assert (await api().get(ruta)).status_code == 404


# --- T-113: IP del cliente ---------------------------------------------------------


def _peticion(host: str | None, cabeceras: dict[str, str], cabecera_ip: str | None) -> Request:
    estado = SimpleNamespace() if cabecera_ip is None else SimpleNamespace(cabecera_ip=cabecera_ip)
    scope = {
        "type": "http",
        "headers": [(k.lower().encode(), v.encode()) for k, v in cabeceras.items()],
        "client": (host, 50000) if host else None,
        "app": SimpleNamespace(state=estado),
    }
    return Request(scope)


CF = {"CF-Connecting-IP": "203.0.113.7"}


@pytest.mark.parametrize(
    ("host", "cabeceras", "variable", "esperada"),
    [
        ("127.0.0.1", CF, None, "127.0.0.1"),  # sin la variable la cabecera se ignora
        ("127.0.0.1", CF, "", "127.0.0.1"),
        ("127.0.0.1", CF, "CF-Connecting-IP", "203.0.113.7"),  # loopback
        ("::1", CF, "CF-Connecting-IP", "203.0.113.7"),
        ("172.18.0.1", CF, "CF-Connecting-IP", "203.0.113.7"),  # red de Docker
        ("198.51.100.20", CF, "CF-Connecting-IP", "198.51.100.20"),  # conexión pública: se ignora
        ("8.8.8.8", CF, "CF-Connecting-IP", "8.8.8.8"),
        (
            "203.0.113.5",
            CF,
            "CF-Connecting-IP",
            "203.0.113.5",
        ),  # rango de documentación: no es red interna
        ("100.64.0.1", CF, "CF-Connecting-IP", "100.64.0.1"),
        ("192.168.1.10", CF, "CF-Connecting-IP", "203.0.113.7"),
        ("fd00::1", CF, "CF-Connecting-IP", "203.0.113.7"),
        ("127.0.0.1", {}, "CF-Connecting-IP", "127.0.0.1"),  # cabecera ausente
        ("127.0.0.1", {"CF-Connecting-IP": "no-es-ip"}, "CF-Connecting-IP", "127.0.0.1"),
        ("127.0.0.1", {"CF-Connecting-IP": ""}, "CF-Connecting-IP", "127.0.0.1"),
        # X-Forwarded-For: vale el último, el que añadió el proxy de confianza.
        (
            "127.0.0.1",
            {"X-Forwarded-For": "1.1.1.1, 203.0.113.7"},
            "X-Forwarded-For",
            "203.0.113.7",
        ),
        ("127.0.0.1", {"X-Forwarded-For": "2001:db8::1"}, "X-Forwarded-For", "2001:db8::1"),
    ],
)
def test_ip_del_cliente(host, cabeceras, variable, esperada):
    assert ip_cliente(_peticion(host, cabeceras, variable)) == esperada


def test_ip_sin_cliente_conocido():
    assert ip_cliente(_peticion(None, CF, "CF-Connecting-IP")) is None


async def test_el_limitador_de_login_distingue_clientes_tras_el_mismo_proxy(
    api, sesion_bd, monkeypatch
):
    """Con CLIENT_IP_HEADER, 5 fallos de un cliente no bloquean al otro (mismo proxy)."""
    monkeypatch.setattr(app.state, "cabecera_ip", "CF-Connecting-IP", raising=False)
    usuario = await crear_usuario_con_clave(sesion_bd, "cliente")
    http = api("127.0.0.1")  # todos llegan por el túnel local
    mal = {"usuario": usuario.usuario, "clave": "equivocada-123"}
    for _ in range(5):
        r = await http.post("/auth/login", json=mal, headers={"CF-Connecting-IP": "203.0.113.1"})
        assert r.status_code == 401
    bloqueado = await http.post(
        "/auth/login", json=mal, headers={"CF-Connecting-IP": "203.0.113.1"}
    )
    assert bloqueado.status_code == 429
    otro = await http.post(
        "/auth/login",
        json={"usuario": usuario.usuario, "clave": CLAVE},
        headers={"CF-Connecting-IP": "203.0.113.2"},
    )
    assert otro.status_code == 200


async def test_sin_la_variable_una_cabecera_falsa_no_evade_el_limitador(
    api, sesion_bd, monkeypatch
):
    monkeypatch.delattr(app.state, "cabecera_ip", raising=False)
    usuario = await crear_usuario_con_clave(sesion_bd, "cliente")
    http = api("198.51.100.30")
    mal = {"usuario": usuario.usuario, "clave": "equivocada-123"}
    for i in range(5):
        await http.post("/auth/login", json=mal, headers={"CF-Connecting-IP": f"203.0.113.{i}"})
    r = await http.post("/auth/login", json=mal, headers={"CF-Connecting-IP": "203.0.113.99"})
    assert r.status_code == 429


# --- T-114: límite de validación ---------------------------------------------------


class Reloj:
    def __init__(self) -> None:
        self.ahora = 1000.0

    def __call__(self) -> float:
        return self.ahora


def test_limitador_por_usuario_rechaza_sin_esperar_y_se_libera():
    reloj = Reloj()
    limitador = LimitadorPorUsuario(3, 60.0, reloj=reloj)
    assert [limitador.intentar("a") for _ in range(4)] == [True, True, True, False]
    assert limitador.intentar("b") is True  # otro usuario no se ve afectado
    reloj.ahora += 59.9
    assert limitador.intentar("a") is False  # un rechazo no registra ni extiende la ventana
    reloj.ahora += 0.2
    assert limitador.intentar("a") is True
    reloj.ahora += 1000
    assert limitador.intentar("c") and set(limitador._marcas) == {"c"}  # se barren las vacías


def test_limitador_por_usuario_valida_los_parametros():
    with pytest.raises(ValueError):
        LimitadorPorUsuario(0)
    with pytest.raises(ValueError):
        LimitadorPorUsuario(1, 0)


async def test_la_validacion_11_recibe_429_sin_llamar_a_ventasff(api, sesion_bd, simulador):
    http, _, paquete = await cliente_web(api, sesion_bd, simulador)
    otro, _, _ = await cliente_web(api, sesion_bd, simulador)
    cuerpo = {"player_id": "75807448", "paquete_id": paquete.paquete_id}
    for _ in range(10):
        assert (await http.post("/recargas/validar", json=cuerpo)).status_code == 200
    antes = list(simulador.peticiones)
    r = await http.post("/recargas/validar", json=cuerpo)
    assert r.status_code == 429
    assert r.json()["detail"].startswith("Demasiadas verificaciones")
    assert simulador.peticiones == antes  # no se llamó a VentasFF
    # Otro cliente conserva su cupo.
    assert (await otro.post("/recargas/validar", json=cuerpo)).status_code == 200


async def test_la_web_muestra_el_429_bajo_el_campo_del_id(api, sesion_bd, simulador):
    http, _, _ = await cliente_web(api, sesion_bd, simulador)
    for _ in range(10):
        assert (
            await htmx_post(http, "/recargar/validar", {"player_id": "75807448"})
        ).status_code == 200
    r = await htmx_post(http, "/recargar/validar", {"player_id": "75807448"})
    assert r.status_code == 429
    assert "Demasiadas verificaciones" in r.text
    assert r.headers["hx-retarget"] == "#mensaje-id"
