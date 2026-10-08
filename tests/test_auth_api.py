"""T-050: login/logout, sesión por cookie, CSRF, bloqueo y limitador (RF-01, RF-04 a RF-07)."""

from sqlalchemy import select, text, update

from app.models import Sesion, Usuario
from app.services.sesiones import hash_token
from tests.utilidades_api import CLAVE, crear_usuario_con_clave, iniciar_sesion


async def test_login_crea_sesion_con_cookie_httponly(api, sesion_bd):
    usuario = await crear_usuario_con_clave(sesion_bd)
    c = api()
    # RF-07: el login no distingue mayúsculas ni espacios alrededor.
    respuesta = await iniciar_sesion(c, f"  {usuario.usuario.upper()} ")
    assert respuesta.status_code == 200
    datos = respuesta.json()
    assert datos["usuario"] == usuario.usuario
    assert datos["rol"] == "cliente"
    assert datos["debe_cambiar_clave"] is False
    assert datos["csrf"]

    cookie = respuesta.headers["set-cookie"].lower()
    assert "sesion=" in cookie and "httponly" in cookie and "samesite=lax" in cookie
    assert "secure" not in cookie  # COOKIE_SECURE=false (RNF-11)

    # Solo se guarda el hash del token, nunca el token.
    token = c.cookies["sesion"]
    registro = await sesion_bd.scalar(select(Sesion).where(Sesion.usuario_id == usuario.id))
    assert registro.token_hash == hash_token(token) != token

    actual = await c.get("/auth/sesion")
    assert actual.status_code == 200
    assert actual.json()["csrf"] == datos["csrf"]


async def test_cookie_secure_segun_configuracion(api, sesion_bd):
    from app.main import app

    usuario = await crear_usuario_con_clave(sesion_bd)
    c = api()
    app.state.cookie_secure = True
    respuesta = await iniciar_sesion(c, usuario.usuario)
    assert "secure" in respuesta.headers["set-cookie"].lower()


async def test_credenciales_incorrectas_mensaje_generico(api, sesion_bd):
    usuario = await crear_usuario_con_clave(sesion_bd)
    c = api()
    mala = await iniciar_sesion(c, usuario.usuario, "otra-clave-x")
    inexistente = await iniciar_sesion(c, "no_existe_nadie", CLAVE)
    assert mala.status_code == inexistente.status_code == 401
    assert mala.json() == inexistente.json()
    assert "sesion" not in c.cookies


async def test_sin_sesion_o_token_invalido_401(api):
    c = api()
    assert (await c.get("/auth/sesion")).status_code == 401
    c.cookies.set("sesion", "inventado")
    assert (await c.get("/auth/sesion")).status_code == 401


async def test_logout_exige_csrf_e_invalida_la_sesion(api, sesion_bd):
    usuario = await crear_usuario_con_clave(sesion_bd)
    c = api()
    await iniciar_sesion(c, usuario.usuario)
    csrf = c.headers.pop("X-CSRF-Token")

    sin_token = await c.post("/auth/logout")
    otro_token = await c.post("/auth/logout", headers={"X-CSRF-Token": "x" + csrf})
    assert sin_token.status_code == otro_token.status_code == 403

    token = c.cookies["sesion"]
    salida = await c.post("/auth/logout", headers={"X-CSRF-Token": csrf})
    assert salida.status_code == 204
    # La cookie vieja ya no sirve aunque el navegador la reenvíe (RF-06).
    c.cookies.set("sesion", token)
    assert (await c.get("/auth/sesion")).status_code == 401


async def test_usuario_bloqueado_no_entra_ni_usa_sesiones(api, sesion_bd):
    usuario = await crear_usuario_con_clave(sesion_bd)
    c = api()
    await iniciar_sesion(c, usuario.usuario)
    await sesion_bd.execute(update(Usuario).where(Usuario.id == usuario.id).values(activo=False))
    await sesion_bd.commit()

    # RF-04: la sesión abierta deja de valer y se borra.
    assert (await c.get("/auth/sesion")).status_code == 401
    restantes = await sesion_bd.scalar(
        select(text("count(*)")).select_from(Sesion).where(Sesion.usuario_id == usuario.id)
    )
    assert restantes == 0
    respuesta = await iniciar_sesion(api(), usuario.usuario)
    assert respuesta.status_code == 403
    assert "bloqueada" in respuesta.json()["detail"]


async def test_sesion_vence_tras_8_horas_sin_actividad(api, sesion_bd):
    usuario = await crear_usuario_con_clave(sesion_bd)
    activa, vencida = api(), api()
    await iniciar_sesion(activa, usuario.usuario)
    await iniciar_sesion(vencida, usuario.usuario)
    hash_activa = hash_token(activa.cookies["sesion"])
    hash_vencida = hash_token(vencida.cookies["sesion"])
    await sesion_bd.execute(
        text(
            "UPDATE sesiones SET ultima_actividad = now() - CASE token_hash "
            "WHEN :activa THEN interval '7 hours 59 minutes' "
            "ELSE interval '8 hours 1 second' END "
            "WHERE token_hash IN (:activa, :vencida)"
        ),
        {"activa": hash_activa, "vencida": hash_vencida},
    )
    await sesion_bd.commit()

    assert (await vencida.get("/auth/sesion")).status_code == 401
    assert (await activa.get("/auth/sesion")).status_code == 200
    # La actividad renueva el plazo de la sesión activa.
    filas = dict(
        (
            await sesion_bd.execute(
                select(Sesion.token_hash, text("now() - ultima_actividad < interval '1 minute'"))
                .where(Sesion.usuario_id == usuario.id)
                .execution_options(populate_existing=True)
            )
        ).all()
    )
    assert filas == {hash_activa: True}


async def test_limitador_por_usuario_e_ip(api, sesion_bd):
    usuario = await crear_usuario_con_clave(sesion_bd)
    c = api("10.1.1.1")
    for _ in range(5):
        assert (await iniciar_sesion(c, usuario.usuario, "mala-clave-1")).status_code == 401
    # RF-05: bloqueado aunque ahora la clave sea correcta.
    bloqueado = await iniciar_sesion(c, usuario.usuario)
    assert bloqueado.status_code == 429
    # Desde otra IP el mismo usuario entra.
    assert (await iniciar_sesion(api("10.1.1.2"), usuario.usuario)).status_code == 200


async def test_limitador_por_ip(api, sesion_bd):
    usuario = await crear_usuario_con_clave(sesion_bd)
    c = api("10.2.2.2")
    for i in range(20):
        await iniciar_sesion(c, f"nadie_{i}", "mala-clave-1")
    assert (await iniciar_sesion(c, usuario.usuario)).status_code == 429
