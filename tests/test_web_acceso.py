"""T-071: páginas de entrar, cambio de contraseña y salir (RF-01, RF-02, RF-04, RF-06, RF-08)."""

from sqlalchemy import select

from app.models import Usuario
from tests.utilidades_api import CLAVE, crear_usuario_con_clave
from tests.utilidades_web import HTMX, csrf_de, htmx_get, htmx_post

NUEVA = "otra-clave-segura-2"


async def test_entrar_muestra_formulario_sin_token(api):
    respuesta = await api().get("/entrar")
    assert respuesta.status_code == 200
    assert 'hx-post="/entrar"' in respuesta.text
    assert "X-CSRF-Token" not in respuesta.text
    assert "/static/htmx.min.js" in respuesta.text


async def test_sin_sesion_redirige_a_entrar(api):
    cliente = api()
    for ruta in ("/", "/clave"):
        respuesta = await cliente.get(ruta)
        assert (respuesta.status_code, respuesta.headers["location"]) == (303, "/entrar")
    respuesta = await htmx_get(cliente, "/clave")
    assert respuesta.headers["HX-Redirect"] == "/entrar"


async def test_credenciales_incorrectas_muestran_mensaje(api, sesion_bd):
    usuario = await crear_usuario_con_clave(sesion_bd)
    respuesta = await htmx_post(api(), "/entrar", {"usuario": usuario.usuario, "clave": "mala"})
    assert respuesta.status_code == 401
    assert "Usuario o contraseña incorrectos." in respuesta.text
    assert "set-cookie" not in respuesta.headers


async def test_usuario_bloqueado_no_entra(api, sesion_bd):
    usuario = await crear_usuario_con_clave(sesion_bd, activo=False)
    respuesta = await htmx_post(api(), "/entrar", {"usuario": usuario.usuario, "clave": CLAVE})
    assert respuesta.status_code == 403
    assert 'class="mensaje error"' in respuesta.text


async def test_cliente_entra_y_va_a_su_inicio(api, sesion_bd):
    usuario = await crear_usuario_con_clave(sesion_bd)
    cliente = api()
    respuesta = await htmx_post(
        cliente, "/entrar", {"usuario": usuario.usuario.upper(), "clave": CLAVE}
    )
    assert respuesta.headers["HX-Redirect"] == "/"
    assert "sesion" in cliente.cookies
    respuesta = await cliente.get("/")
    assert respuesta.headers["location"] == "/inicio"
    # Con sesión, /entrar lleva al inicio.
    assert (await cliente.get("/entrar")).headers["location"] == "/inicio"


async def test_admin_va_al_panel(api, sesion_bd):
    usuario = await crear_usuario_con_clave(sesion_bd, rol="admin")
    cliente = api()
    await htmx_post(cliente, "/entrar", {"usuario": usuario.usuario, "clave": CLAVE})
    assert (await cliente.get("/")).headers["location"] == "/gestion"


async def test_cambio_obligatorio_de_clave(api, sesion_bd):
    usuario = await crear_usuario_con_clave(sesion_bd, debe_cambiar_clave=True)
    cliente = api()
    respuesta = await htmx_post(cliente, "/entrar", {"usuario": usuario.usuario, "clave": CLAVE})
    assert respuesta.headers["HX-Redirect"] == "/clave"
    # RF-02: mientras no la cambie, todo lleva a /clave.
    assert (await cliente.get("/")).headers["location"] == "/clave"

    pagina = await cliente.get("/clave")
    assert pagina.status_code == 200
    assert "Debes cambiar tu contraseña temporal" in pagina.text
    cliente.headers["X-CSRF-Token"] = csrf_de(pagina.text)

    respuesta = await htmx_post(cliente, "/clave", {"clave_actual": CLAVE, "clave_nueva": NUEVA})
    assert respuesta.headers["HX-Redirect"] == "/"
    assert (await cliente.get("/")).headers["location"] == "/inicio"
    guardado = await sesion_bd.scalar(
        select(Usuario).where(Usuario.id == usuario.id).execution_options(populate_existing=True)
    )
    assert guardado.debe_cambiar_clave is False


async def test_cambio_de_clave_rechazos(api, sesion_bd):
    usuario = await crear_usuario_con_clave(sesion_bd, debe_cambiar_clave=True)
    cliente = api()
    await htmx_post(cliente, "/entrar", {"usuario": usuario.usuario, "clave": CLAVE})

    # Sin token CSRF.
    respuesta = await htmx_post(cliente, "/clave", {"clave_actual": CLAVE, "clave_nueva": NUEVA})
    assert respuesta.status_code == 403
    assert "Token CSRF" in respuesta.text

    cliente.headers["X-CSRF-Token"] = csrf_de((await cliente.get("/clave")).text)
    respuesta = await htmx_post(cliente, "/clave", {"clave_actual": "mala", "clave_nueva": NUEVA})
    assert (respuesta.status_code, "La contraseña actual es incorrecta." in respuesta.text) == (
        400,
        True,
    )
    respuesta = await htmx_post(cliente, "/clave", {"clave_actual": CLAVE, "clave_nueva": "corta"})
    assert respuesta.status_code == 400
    assert 'class="mensaje error"' in respuesta.text


async def test_salir_cierra_la_sesion(api, sesion_bd):
    usuario = await crear_usuario_con_clave(sesion_bd, debe_cambiar_clave=True)
    cliente = api()
    await htmx_post(cliente, "/entrar", {"usuario": usuario.usuario, "clave": CLAVE})
    cliente.headers["X-CSRF-Token"] = csrf_de((await cliente.get("/clave")).text)

    respuesta = await cliente.post("/salir", headers=HTMX)
    assert respuesta.headers["HX-Redirect"] == "/entrar"
    assert (await cliente.get("/clave")).headers["location"] == "/entrar"
