"""T-116 a T-118: topes de intentos de login, de pedidos y de peticiones (CHG-019).

RF-05 (tope por cuenta), RF-57 (5 pedidos por minuto y cliente), RNF-17 (tope general
de peticiones), con RF-25 (el reenvío con el mismo token también cuenta) y RNF-16 (la
IP anónima es la de `CLIENT_IP_HEADER`). Los topes reales son de 120 y 60 por minuto:
las pruebas HTTP usan topes pequeños y una prueba aparte fija los valores de la spec.
"""

import inspect
import uuid

from app import main
from app.services import limitador
from app.services.limitador import LimitadorPorUsuario
from tests.utilidades_api import CLAVE, crear_usuario_con_clave, iniciar_sesion
from tests.utilidades_web import cliente_web, htmx_post


class Reloj:
    def __init__(self) -> None:
        self.ahora = 1000.0

    def __call__(self) -> float:
        return self.ahora


def _estado():
    return main.app.state


# --- Valores de la spec ------------------------------------------------------------


def test_los_topes_coinciden_con_la_spec():
    """RF-57 (5/min por cliente) y RNF-17 (120/min por usuario, 60/min por IP)."""
    assert limitador.PEDIDOS_POR_MINUTO == 5
    assert limitador.PETICIONES_USUARIO_POR_MINUTO == 120
    assert limitador.PETICIONES_ANONIMAS_POR_MINUTO == 60
    codigo = inspect.getsource(main.lifespan)
    for atributo, constante in (
        ("limitador_pedidos", "PEDIDOS_POR_MINUTO"),
        ("limitador_peticiones", "PETICIONES_USUARIO_POR_MINUTO"),
        ("limitador_anonimo", "PETICIONES_ANONIMAS_POR_MINUTO"),
    ):
        assert f"app.state.{atributo} = LimitadorPorUsuario({constante})" in codigo


# --- T-116: tope por cuenta en el login (RF-05) -------------------------------------


async def test_diez_fallos_desde_ips_distintas_bloquean_la_cuenta(api, sesion_bd):
    usuario = await crear_usuario_con_clave(sesion_bd, "cliente")
    otro = await crear_usuario_con_clave(sesion_bd, "cliente")
    for n in range(1, 11):
        r = await api(f"203.0.113.{n}").post(
            "/auth/login", json={"usuario": usuario.usuario, "clave": "incorrecta-1"}
        )
        assert r.status_code == 401
    # Desde una IP limpia, ni la clave correcta entra: la cuenta está bloqueada (RF-05).
    r = await api("198.51.100.77").post(
        "/auth/login", json={"usuario": usuario.usuario, "clave": CLAVE}
    )
    assert r.status_code == 429
    assert r.json()["detail"].startswith("Demasiados intentos fallidos")
    # Otra cuenta desde la misma IP no se ve afectada.
    assert (await iniciar_sesion(api("198.51.100.77"), otro.usuario)).status_code == 200


async def test_nueve_fallos_no_bloquean_la_cuenta(api, sesion_bd):
    usuario = await crear_usuario_con_clave(sesion_bd, "cliente")
    for n in range(1, 10):
        await api(f"203.0.113.{n}").post(
            "/auth/login", json={"usuario": usuario.usuario, "clave": "incorrecta-1"}
        )
    assert (await iniciar_sesion(api("198.51.100.77"), usuario.usuario)).status_code == 200


# --- T-117: tope de pedidos por cliente (RF-57) -------------------------------------


def _cuerpo(paquete_id: int, token: str | None = None) -> dict:
    return {
        "paquete_id": paquete_id,
        "player_id": "75807448",
        "token_idempotencia": token or uuid.uuid4().hex,
    }


async def test_el_pedido_6_recibe_429_sin_reservar_ni_llamar_a_ventasff(api, sesion_bd, simulador):
    _estado().limitador_pedidos = LimitadorPorUsuario(limitador.PEDIDOS_POR_MINUTO)
    http, _, paquete = await cliente_web(api, sesion_bd, simulador, abono="10.00")
    otro, _, paquete_otro = await cliente_web(api, sesion_bd, simulador, abono="10.00")
    for _ in range(5):
        assert (await http.post("/recargas", json=_cuerpo(paquete.paquete_id))).status_code == 201
    peticiones, recargas = list(simulador.peticiones), len(simulador.recargas)
    saldo_antes = (await http.get("/me/resumen")).json()["saldo_disponible"]

    r = await http.post("/recargas", json=_cuerpo(paquete.paquete_id))
    assert r.status_code == 429
    assert r.json()["detail"] == "Demasiadas recargas. Espera un momento e inténtalo de nuevo."
    assert simulador.peticiones == peticiones and len(simulador.recargas) == recargas
    assert (await http.get("/me/resumen")).json()["saldo_disponible"] == saldo_antes
    # Otro cliente conserva su cupo.
    assert (await otro.post("/recargas", json=_cuerpo(paquete_otro.paquete_id))).status_code == 201


async def test_el_reenvio_con_el_mismo_token_cuenta_y_los_rechazos_no(api, sesion_bd, simulador):
    reloj = Reloj()
    limite = LimitadorPorUsuario(5, 60.0, reloj=reloj)
    _estado().limitador_pedidos = limite
    http, usuario, paquete = await cliente_web(api, sesion_bd, simulador, abono="10.00")
    cuerpo = _cuerpo(paquete.paquete_id)
    assert (await http.post("/recargas", json=cuerpo)).status_code == 201
    for _ in range(4):  # RF-25: el mismo token devuelve el pedido, pero consume cupo
        assert (await http.post("/recargas", json=cuerpo)).status_code == 200
    for _ in range(3):
        assert (await http.post("/recargas", json=cuerpo)).status_code == 429
    assert len(limite._marcas[usuario.id]) == 5  # los rechazos no cuentan
    # La ventana se libera con el tiempo.
    reloj.ahora += 61
    assert (await http.post("/recargas", json=cuerpo)).status_code == 200


async def test_la_web_muestra_el_429_en_el_mensaje_de_confirmacion(api, sesion_bd, simulador):
    _estado().limitador_pedidos = LimitadorPorUsuario(2)
    http, _, paquete = await cliente_web(api, sesion_bd, simulador, abono="10.00")
    for _ in range(2):
        formulario = {**_cuerpo(paquete.paquete_id), "paquete_id": str(paquete.paquete_id)}
        assert (await htmx_post(http, "/recargar/confirmar", formulario)).status_code == 200
    r = await htmx_post(http, "/recargar/confirmar", _cuerpo(paquete.paquete_id))
    assert r.status_code == 429
    assert "Demasiadas recargas" in r.text
    assert r.headers["hx-retarget"] == "#mensaje-confirmacion"


# --- T-118: tope general de peticiones (RNF-17) -------------------------------------


async def test_la_peticion_n_mas_1_de_un_usuario_recibe_429(api, sesion_bd, simulador):
    http, usuario, _ = await cliente_web(api, sesion_bd, simulador)
    otro, _, _ = await cliente_web(api, sesion_bd, simulador)
    limite = LimitadorPorUsuario(3)
    _estado().limitador_peticiones = limite
    for _ in range(3):
        assert (await http.get("/me/resumen")).status_code == 200
    r = await http.get("/me/resumen")
    assert r.status_code == 429
    assert r.json()["detail"] == "Demasiadas peticiones. Espera un momento e inténtalo de nuevo."
    assert len(limite._marcas[usuario.id]) == 3  # el rechazo no cuenta
    assert (await otro.get("/me/resumen")).status_code == 200  # otro usuario, otro cupo


async def test_con_sesion_valida_el_429_no_redirige_al_login(api, sesion_bd, simulador):
    http, _, _ = await cliente_web(api, sesion_bd, simulador)
    _estado().limitador_peticiones = LimitadorPorUsuario(1)
    assert (await http.get("/inicio")).status_code == 200
    for ruta in ("/inicio", "/login", "/"):  # incluso en las rutas con sesión opcional
        r = await http.get(ruta, follow_redirects=False)
        assert r.status_code == 429, ruta
        assert "location" not in r.headers
        assert "Demasiadas peticiones" in r.text


async def test_sin_sesion_el_tope_es_por_ip_y_cubre_el_login(api, simulador):
    limite = LimitadorPorUsuario(3)
    _estado().limitador_anonimo = limite
    http = api("203.0.113.5")
    assert (await http.get("/login")).status_code == 200
    assert (await http.get("/auth/sesion")).status_code == 401  # sesión ausente cuenta
    r = await http.post("/auth/login", json={"usuario": "nadie", "clave": "x" * 10})
    assert r.status_code == 401  # el login cuenta (3.ª)
    r = await http.post("/auth/login", json={"usuario": "nadie", "clave": "x" * 10})
    assert r.status_code == 429
    assert r.json()["detail"].startswith("Demasiadas peticiones")
    assert len(limite._marcas["203.0.113.5"]) == 3  # el rechazo no cuenta
    # La web de login también lo cumple y lo muestra.
    web = await htmx_post(http, "/login", {"usuario": "nadie", "clave": "x" * 10})
    assert web.status_code == 429 and "Demasiadas peticiones" in web.text
    # Otra IP tiene su propio cupo.
    assert (await api("203.0.113.6").get("/login")).status_code == 200


async def test_estaticos_y_health_no_cuentan(api, simulador):
    limite = LimitadorPorUsuario(1)
    _estado().limitador_anonimo = limite
    _estado().limitador_peticiones = limite
    http = api("203.0.113.9")
    for _ in range(3):
        assert (await http.get("/static/app.css")).status_code == 200
        assert (await http.get("/health")).status_code == 200
    assert limite._marcas == {}


async def test_la_ip_anonima_es_la_de_client_ip_header(api, simulador):
    """RNF-16: tras el proxy, cada cliente real tiene su propio cupo anónimo."""
    estado = _estado()
    estado.limitador_anonimo = LimitadorPorUsuario(1)
    estado.cabecera_ip = "CF-Connecting-IP"
    try:
        http = api("127.0.0.1")  # el proxy local
        uno = await http.get("/login", headers={"CF-Connecting-IP": "198.51.100.1"})
        otro = await http.get("/login", headers={"CF-Connecting-IP": "198.51.100.2"})
        repetido = await http.get("/login", headers={"CF-Connecting-IP": "198.51.100.1"})
    finally:
        estado.cabecera_ip = ""
    assert (uno.status_code, otro.status_code, repetido.status_code) == (200, 200, 429)
