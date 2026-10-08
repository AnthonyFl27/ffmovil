"""T-061: `require_admin` protege todas las rutas `/admin/*` (RNF-03)."""

import re

from app.main import app
from tests.utilidades_api import crear_usuario_con_clave, iniciar_sesion


def rutas_admin() -> list[tuple[str, str]]:
    rutas = []
    for ruta, metodos in app.openapi()["paths"].items():
        if ruta.startswith("/admin"):
            concreta = re.sub(r"\{[^}]+\}", "1", ruta)
            rutas.extend((metodo.upper(), concreta) for metodo in metodos)
    return sorted(rutas)


async def test_cliente_recibe_403_y_anonimo_401_en_todo_admin(api, sesion_bd):
    rutas = rutas_admin()
    assert len(rutas) >= 18
    cliente = await crear_usuario_con_clave(sesion_bd)
    c, anonimo = api(), api()
    await iniciar_sesion(c, cliente.usuario)
    for metodo, ruta in rutas:
        como_cliente = await c.request(metodo, ruta, json={})
        assert como_cliente.status_code == 403, (metodo, ruta, como_cliente.text)
        assert como_cliente.json()["detail"] == "Acceso solo para administradores."
        sin_sesion = await anonimo.request(metodo, ruta, json={})
        assert sin_sesion.status_code == 401, (metodo, ruta)


async def test_admin_que_debe_cambiar_clave_tampoco_entra(api, sesion_bd):
    admin = await crear_usuario_con_clave(sesion_bd, rol="admin", debe_cambiar_clave=True)
    c = api()
    await iniciar_sesion(c, admin.usuario)
    assert (await c.get("/admin/panel")).status_code == 403
