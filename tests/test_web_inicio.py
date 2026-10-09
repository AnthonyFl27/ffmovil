"""T-072: inicio del cliente con saldo, gasto total, nº de recargas y botones (RF-33)."""

from app.services.codigos import codigo_pedido
from tests.utilidades import crear_pedido
from tests.utilidades_api import crear_usuario_con_clave, iniciar_sesion
from tests.utilidades_web import cliente_web, csrf_de


async def test_inicio_muestra_resumen(api, sesion_bd):
    http, usuario, paquete = await cliente_web(api, sesion_bd)
    # Solo los EXITOSO cuentan en gasto y recargas (RF-33).
    for estado in ("EXITOSO", "EXITOSO", "FALLIDO"):
        pedido = await crear_pedido(sesion_bd, usuario.id, paquete, estado=estado)
        pedido.codigo = codigo_pedido(pedido.id)
    await sesion_bd.commit()

    respuesta = await http.get("/inicio")
    assert respuesta.status_code == 200
    html = respuesta.text
    assert '<strong id="saldo-disponible">10.00 USD</strong>' in html
    assert '<strong id="gasto-total">1.50 USD</strong>' in html
    assert '<strong id="recargas">2</strong>' in html
    assert 'href="/recargar"' in html and 'href="/historial"' in html
    assert csrf_de(html) == http.headers["X-CSRF-Token"]


async def test_inicio_sin_movimientos(api, sesion_bd):
    usuario = await crear_usuario_con_clave(sesion_bd)
    http = api()
    await iniciar_sesion(http, usuario.usuario)
    html = (await http.get("/inicio")).text
    assert '<strong id="saldo-disponible">0.00 USD</strong>' in html
    assert '<strong id="recargas">0</strong>' in html
    # RF-33: sin recargas, estado vacío con acceso a Recargar.
    assert "Todavía no tienes recargas." in html and "Hacer mi primera recarga" in html
    assert 'class="recientes"' not in html


async def test_admin_no_ve_el_inicio_del_cliente(api, sesion_bd):
    admin = await crear_usuario_con_clave(sesion_bd, rol="admin")
    http = api()
    await iniciar_sesion(http, admin.usuario)
    for ruta in ("/inicio", "/recargar", "/historial", "/fondos"):
        respuesta = await http.get(ruta)
        assert (respuesta.status_code, respuesta.headers["location"]) == (303, "/gestion")


async def test_cliente_que_debe_cambiar_clave_va_a_clave(api, sesion_bd):
    usuario = await crear_usuario_con_clave(sesion_bd, debe_cambiar_clave=True)
    http = api()
    await iniciar_sesion(http, usuario.usuario)
    assert (await http.get("/inicio")).headers["location"] == "/clave"


async def test_inicio_ultimas_cinco_recargas_de_cualquier_estado(api, sesion_bd):
    http, usuario, paquete = await cliente_web(api, sesion_bd)
    ajeno = await crear_usuario_con_clave(sesion_bd)
    pedidos = [
        await crear_pedido(sesion_bd, usuario.id, paquete, estado=estado, nickname=f"Jugador{n}")
        for n, estado in enumerate(
            ("EXITOSO", "EXITOSO", "EXITOSO", "EXITOSO", "FALLIDO", "PENDIENTE_VERIFICAR"), 1
        )
    ]
    for pedido in pedidos:
        pedido.codigo = codigo_pedido(pedido.id)
    ajeno_pedido = await crear_pedido(sesion_bd, ajeno.id, paquete, estado="EXITOSO")
    ajeno_pedido.codigo = codigo_pedido(ajeno_pedido.id)
    await sesion_bd.commit()

    html = (await http.get("/inicio")).text
    # Solo las 5 más recientes y propias; incluye fallidas y en revisión (RF-33).
    assert html.count('href="/historial/FF-') == 5
    assert f'href="/historial/{pedidos[-1].codigo}"' in html
    assert f'href="/historial/{pedidos[0].codigo}"' not in html
    assert f'href="/historial/{ajeno_pedido.codigo}"' not in html
    assert "Fallido" in html and "En revisión" in html and "Jugador6" in html
    assert 'href="/historial">Ver todo</a>' in html
    assert "costo" not in html.lower() and "ganancia" not in html.lower()
