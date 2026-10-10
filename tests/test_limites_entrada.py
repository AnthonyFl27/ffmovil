"""T-110: límites de entrada (RNF-13, CHG-016)."""

import httpx

from app.limite_cuerpo import LIMITE_CUERPO_BYTES, LimiteCuerpo
from app.services import auth_service
from tests.utilidades_api import CLAVE, crear_usuario_con_clave, iniciar_sesion


async def _eco(scope, receive, send):
    """App mínima: lee todo el cuerpo y responde 200 con su tamaño."""
    total = 0
    while True:
        mensaje = await receive()
        total += len(mensaje.get("body", b""))
        if not mensaje.get("more_body"):
            break
    await send({"type": "http.response.start", "status": 200, "headers": []})
    await send({"type": "http.response.body", "body": str(total).encode()})


def _cliente(app) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t")


async def test_cuerpo_de_64kb_exactos_pasa_y_uno_mas_no():
    async with _cliente(LimiteCuerpo(_eco)) as http:
        justo = await http.post("/", content=b"x" * LIMITE_CUERPO_BYTES)
        assert (justo.status_code, justo.text) == (200, str(LIMITE_CUERPO_BYTES))
        grande = await http.post("/", content=b"x" * (LIMITE_CUERPO_BYTES + 1))
        assert grande.status_code == 413
        assert "demasiado grande" in grande.json()["detail"]


async def test_flujo_sin_content_length_se_corta_con_413():
    """Transferencia por trozos: no hay cabecera que revisar, se cuenta lo recibido."""

    async def trozos():
        for _ in range(LIMITE_CUERPO_BYTES // 1024 + 2):
            yield b"x" * 1024

    async with _cliente(LimiteCuerpo(_eco)) as http:
        respuesta = await http.post("/", content=trozos())
        assert respuesta.status_code == 413


async def test_413_aunque_la_app_convierta_el_error_en_400(api):
    """FastAPI traduce los errores al leer el cuerpo en 400: el límite debe ganar."""

    async def trozos():
        for _ in range(LIMITE_CUERPO_BYTES // 1024 + 2):
            yield b'{"usuario": "' + b"a" * 1000

    respuesta = await api().post("/auth/login", content=trozos())
    assert respuesta.status_code == 413


async def test_cuerpo_grande_en_la_app_real_da_413_sin_tocar_la_bd(api):
    declarado = await api().post("/auth/login", json={"usuario": "u", "clave": "x" * 70_000})
    assert declarado.status_code == 413


async def test_login_con_datos_largos_es_401_generico_y_cuenta_como_fallo(
    api, sesion_bd, monkeypatch
):
    llamadas = []

    async def autenticar(*args):
        llamadas.append(args)

    monkeypatch.setattr(auth_service, "autenticar", autenticar)
    http = api("10.1.1.1")
    for datos in (
        {"usuario": "a" * 31, "clave": CLAVE},
        {"usuario": "alguien", "clave": "x" * 129},
    ):
        r = await http.post("/auth/login", json=datos)
        assert r.status_code == 401
        assert r.json()["detail"] == "Usuario o contraseña incorrectos."
    assert not llamadas
    # Cuenta como fallo: tras 5 intentos largos con el mismo usuario e IP, bloquea.
    for _ in range(4):
        await http.post("/auth/login", json={"usuario": "a" * 31, "clave": CLAVE})
    r = await http.post("/auth/login", json={"usuario": "a" * 31, "clave": CLAVE})
    assert r.status_code == 429


async def test_los_topes_exactos_siguen_siendo_validos(api, sesion_bd):
    """30 caracteres de usuario y 128 de clave no se rechazan por el límite."""
    usuario = await crear_usuario_con_clave(sesion_bd, "cliente", clave="c" * 128)
    r = await iniciar_sesion(api(), usuario.usuario, "c" * 128)
    assert r.status_code == 200
    r = await api().post("/auth/login", json={"usuario": "z" * 30, "clave": "c" * 128})
    assert r.status_code == 401
