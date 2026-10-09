"""Adaptación a móvil (RNF-12, CHG-009): estructura de las plantillas.

T-100: el menú plegable trae las mismas opciones que el menú en línea, y "Salir".
T-101: historial y fondos del cliente en tarjetas, filtros plegables y detalle en ficha.
T-102: pantallas admin en tarjetas, filtros plegables y fichas.
"""

import re

from app.services.codigos import codigo_pedido
from tests.utilidades import crear_paquete, crear_pedido
from tests.utilidades_api import crear_usuario_con_clave, iniciar_sesion
from tests.utilidades_web import cliente_web

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


async def test_historial_en_tarjetas_con_filtros_plegables(api, sesion_bd):
    # T-101: cada celda lleva su etiqueta para la tarjeta; el estado siempre se ve.
    http, usuario, paquete = await cliente_web(api, sesion_bd, abono=None)
    pedido = await crear_pedido(sesion_bd, usuario.id, paquete, estado="PENDIENTE_VERIFICAR")
    pedido.codigo = codigo_pedido(pedido.id)
    await sesion_bd.commit()

    html = (await http.get("/historial")).text
    assert '<table class="tarjetas">' in html
    for etiqueta in ("Fecha", "Pedido", "Paquete", "Monto"):
        assert f'<td data-etiqueta="{etiqueta}">' in html
    assert '<td data-etiqueta="Estado" class="estado estado-PENDIENTE_VERIFICAR">' in html
    # Sin filtros activos van plegados; con alguno activo, abiertos.
    assert '<details class="filtros">' in html
    filtrado = (await http.get("/historial", params={"estado": "FALLIDO"})).text
    assert '<details class="filtros" open>' in filtrado


def celdas(html: str) -> list[str]:
    return re.findall(r"<td[^>]*>", html)


async def test_historial_en_tarjetas_con_estado_visible(api, sesion_bd):
    # T-101: cada celda lleva su etiqueta; el estado nunca es secundario (CA-05).
    http, usuario, paquete = await cliente_web(api, sesion_bd)
    pedido = await crear_pedido(sesion_bd, usuario.id, paquete, estado="PENDIENTE_VERIFICAR")
    pedido.codigo = codigo_pedido(pedido.id)
    await sesion_bd.commit()

    html = (await http.get("/historial")).text
    assert '<table class="tarjetas">' in html
    tds = celdas(html)
    assert tds and all("data-etiqueta=" in td for td in tds)
    estado = next(td for td in tds if 'data-etiqueta="Estado"' in td)
    assert "secundario" not in estado
    visibles = [
        re.search(r'data-etiqueta="([^"]+)"', td)[1] for td in tds if "secundario" not in td
    ]
    assert visibles == ["Fecha", "Pedido", "Paquete", "Monto", "Estado"]
    # Sin filtros activos el formulario va plegado; con filtros, abierto.
    assert '<details class="filtros">' in html
    html = (await http.get("/historial", params={"codigo": pedido.codigo})).text
    assert '<details class="filtros" open>' in html


async def test_fondos_en_tarjetas(api, sesion_bd):
    http, _, _ = await cliente_web(api, sesion_bd)
    html = (await http.get("/fondos")).text
    assert '<table class="tarjetas">' in html
    assert all("data-etiqueta=" in td for td in celdas(html))


def tablas_en_tarjetas(html: str) -> None:
    """Toda tabla es de tarjetas y toda celda (salvo las de colspan) lleva etiqueta."""
    assert "<table>" not in html
    assert all("data-etiqueta=" in td for td in celdas(html) if "colspan" not in td)


async def test_pantallas_admin_en_tarjetas(api, sesion_bd):
    # T-102: pedidos, usuarios, auditoría, paquetes, alertas y detalle (RF-50 a RF-55).
    from app.services import alertas, auditoria

    admin = await crear_usuario_con_clave(sesion_bd, rol="admin")
    cliente = await crear_usuario_con_clave(sesion_bd)
    paquete = await crear_paquete(sesion_bd, precio_costo="0.50", precio_venta="0.75")
    pedido = await crear_pedido(sesion_bd, cliente.id, paquete, estado="PENDIENTE_VERIFICAR")
    pedido.codigo = codigo_pedido(pedido.id)
    await alertas.registrar_alerta(sesion_bd, "cuenta", "Alerta de prueba móvil")
    auditoria.registrar(sesion_bd, admin.id, "prueba.movil", {"campo": "valor"}, "203.0.113.1")
    await sesion_bd.commit()
    http = api()
    await iniciar_sesion(http, admin.usuario)

    pedidos = (await http.get("/gestion/pedidos", params={"usuario": cliente.usuario})).text
    assert '<table class="tarjetas">' in pedidos
    tablas_en_tarjetas(pedidos)
    estado = next(td for td in celdas(pedidos) if 'data-etiqueta="Estado"' in td)
    assert "secundario" not in estado
    assert '<details class="filtros" open>' in pedidos

    for ruta in (
        "/gestion",
        "/gestion/usuarios",
        "/gestion/auditoria",
        "/gestion/paquetes",
        f"/gestion/pedidos/{pedido.id}",
    ):
        html = (await http.get(ruta)).text
        assert '<table class="tarjetas">' in html, ruta
        tablas_en_tarjetas(html)
    detalle = (await http.get(f"/gestion/pedidos/{pedido.id}")).text
    assert '<dl class="ficha">' in detalle
    auditoria = (await http.get("/gestion/auditoria")).text
    assert '<details class="filtros">' in auditoria
