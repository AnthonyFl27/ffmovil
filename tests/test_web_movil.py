"""Adaptación a móvil (RNF-12, CHG-009): estructura de las plantillas.

T-100: el menú plegable trae las mismas opciones que el menú en línea, y "Salir".
"""

import re

from tests.utilidades_api import crear_usuario_con_clave, iniciar_sesion

OPCIONES_CLIENTE = ["/inicio", "/recargar", "/historial", "/fondos"]
OPCIONES_ADMIN = [
    "/gestion",
    "/gestion/pedidos",
    "/gestion/usuarios",
    "/gestion/paquetes",
    "/gestion/config",
    "/gestion/auditoria",
]


def menu(html: str, clase: str) -> str:
    encontrado = re.search(rf'<ul class="{clase}">(.*?)</ul>', html, re.DOTALL)
    assert encontrado, f"la página no trae el menú {clase}"
    return encontrado.group(1)


def rutas(fragmento: str) -> list[str]:
    return re.findall(r'<a href="([^"]+)">', fragmento)


async def test_menu_plegable_con_todas_las_opciones(api, sesion_bd):
    cliente = await crear_usuario_con_clave(sesion_bd)
    admin = await crear_usuario_con_clave(sesion_bd, rol="admin")
    for usuario, pagina, opciones in (
        (cliente, "/inicio", OPCIONES_CLIENTE),
        (admin, "/gestion", OPCIONES_ADMIN),
    ):
        http = api()
        await iniciar_sesion(http, usuario.usuario)
        html = (await http.get(pagina)).text
        en_linea, plegable = menu(html, "menu-linea"), menu(html, "menu-plegable")
        assert rutas(en_linea) == rutas(plegable) == opciones
        assert '<details class="dropdown">' in plegable
        assert 'hx-post="/salir"' in en_linea and 'hx-post="/salir"' in plegable
