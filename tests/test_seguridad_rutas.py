"""T-082: inventario de rutas — sesión, CSRF y rol exigidos en todas (RNF-03, RF-04, RF-06).

Recorre todas las rutas registradas en la app, de modo que una ruta nueva sin
protección hace fallar la prueba hasta que se proteja o se declare pública aquí.
"""

import re

from app.main import app
from tests.utilidades_api import crear_usuario_con_clave, iniciar_sesion

PREFIJOS_API = ("/auth", "/me", "/paquetes", "/recargas", "/admin")
METODOS_SEGUROS = {"GET", "HEAD", "OPTIONS"}

# Rutas sin sesión por diseño. `/login` y `/auth/login` autentican con credenciales.
PUBLICAS = {
    "/health",
    "/login",
    "/auth/login",
    "/",  # solo redirige: a /login sin sesión
}


def _recorrer(rutas, prefijo=""):
    for ruta in rutas:
        if hasattr(ruta, "original_router"):
            yield from _recorrer(ruta.original_router.routes, prefijo + ruta.include_context.prefix)
        else:
            yield prefijo, ruta


def _rutas_app() -> list[tuple[str, str]]:
    """(método, ruta con parámetros de ejemplo) de cada ruta de la app."""
    encontradas = []
    for prefijo, ruta in _recorrer(app.routes):
        metodos = getattr(ruta, "methods", None)
        if not metodos:  # montajes, como /static
            continue
        camino = re.sub(r"\{[^}]+\}", "1", prefijo + ruta.path)
        for metodo in sorted(metodos - {"HEAD", "OPTIONS"}):
            encontradas.append((metodo, camino))
    return encontradas


RUTAS = _rutas_app()
PROTEGIDAS = [(m, p) for m, p in RUTAS if p not in PUBLICAS]
NO_SEGURAS = [(m, p) for m, p in PROTEGIDAS if m not in METODOS_SEGUROS]
ADMIN = [(m, p) for m, p in PROTEGIDAS if p.startswith(("/admin", "/gestion"))]
CLIENTE = [
    (m, p)
    for m, p in PROTEGIDAS
    if p.startswith(
        ("/me", "/paquetes", "/recargas", "/recargar", "/historial", "/fondos", "/inicio")
    )
]


def test_el_inventario_encuentra_las_rutas():
    assert len(RUTAS) > 50
    assert ("POST", "/recargas") in RUTAS and ("POST", "/gestion/config") in RUTAS


async def test_sin_sesion_ninguna_ruta_protegida_responde(api):
    """Sin cookie: 401 en la API y redirección a /login en las páginas; nunca 2xx."""
    http = api()
    fallos = []
    for metodo, ruta in PROTEGIDAS:
        r = await http.request(metodo, ruta, follow_redirects=False)
        if ruta.startswith(PREFIJOS_API):
            bien = r.status_code == 401
        else:
            bien = r.status_code in (303, 401) or "hx-redirect" in r.headers
        if not bien or "set-cookie" in r.headers:
            fallos.append((metodo, ruta, r.status_code))
    assert not fallos


async def test_sin_csrf_toda_ruta_que_cambia_estado_responde_403(api, sesion_bd):
    """Con sesión válida pero sin `X-CSRF-Token` o con uno ajeno: 403, la acción no corre."""
    usuario = await crear_usuario_con_clave(sesion_bd, "cliente")
    http = api()
    assert (await iniciar_sesion(http, usuario.usuario)).status_code == 200
    csrf = http.headers.pop("X-CSRF-Token")
    fallos = []
    for metodo, ruta in NO_SEGURAS:
        for cabeceras in ({}, {"X-CSRF-Token": csrf + "x"}):
            r = await http.request(metodo, ruta, headers=cabeceras, follow_redirects=False)
            if r.status_code != 403 or "CSRF" not in r.text:
                fallos.append((metodo, ruta, r.status_code))
    assert not fallos


async def test_un_cliente_no_entra_a_rutas_de_admin(api, sesion_bd):
    usuario = await crear_usuario_con_clave(sesion_bd, "cliente")
    http = api()
    await iniciar_sesion(http, usuario.usuario)
    fallos = []
    for metodo, ruta in ADMIN:
        r = await http.request(metodo, ruta, follow_redirects=False)
        if r.status_code not in (403, 303):
            fallos.append((metodo, ruta, r.status_code))
    assert not fallos


async def test_un_admin_no_entra_a_rutas_de_cliente(api, sesion_bd):
    usuario = await crear_usuario_con_clave(sesion_bd, "admin")
    http = api()
    await iniciar_sesion(http, usuario.usuario)
    fallos = []
    for metodo, ruta in CLIENTE:
        r = await http.request(metodo, ruta, follow_redirects=False)
        if r.status_code not in (403, 303):
            fallos.append((metodo, ruta, r.status_code))
    assert not fallos
