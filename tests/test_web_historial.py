"""T-074: historial con filtros y estados visibles, incluidos fallidos y "En revisión".

RF-30, RF-31, RF-32, CA-05; fechas en la zona del usuario (RNF-09).
"""

from datetime import UTC, datetime

from sqlalchemy import update

from app.models import Pedido
from app.services.codigos import codigo_pedido
from tests.utilidades import crear_pedido
from tests.utilidades_api import crear_usuario_con_clave, iniciar_sesion
from tests.utilidades_web import cliente_web, htmx_get


async def pedido(sesion, usuario, paquete, **cambios):
    creado = await crear_pedido(sesion, usuario.id, paquete, **cambios)
    creado.codigo = codigo_pedido(creado.id)
    return creado


async def preparar(api, sesion):
    http, usuario, paquete = await cliente_web(api, sesion, abono=None)
    exitoso = await pedido(
        sesion, usuario, paquete, estado="EXITOSO", referencia="EV-AAA111", nickname="Ana"
    )
    fallido = await pedido(
        sesion,
        usuario,
        paquete,
        estado="FALLIDO",
        error="La entrega falló",
        error_code="PURCHASE_FAILED",
        player_id="11112222",
    )
    revision = await pedido(sesion, usuario, paquete, estado="PENDIENTE_VERIFICAR")
    await sesion.commit()
    return (
        http,
        usuario,
        (exitoso.codigo, fallido.codigo, revision.codigo),
        (
            exitoso.id,
            fallido.id,
        ),
    )


async def test_historial_muestra_estados_y_motivo(api, sesion_bd):
    http, _, (exitoso, fallido, revision), _ = await preparar(api, sesion_bd)
    respuesta = await http.get("/historial")
    assert respuesta.status_code == 200
    html = respuesta.text
    for codigo in (exitoso, fallido, revision):
        assert f'href="/historial/{codigo}"' in html
    assert "Exitoso" in html and "Fallido" in html and "En revisión" in html
    # CA-05: el fallido aparece con su ID y su motivo.
    assert "La entrega falló" in html
    assert "EV-AAA111" in html and "Ana" in html and "0.75 USD" in html
    assert "3 pedidos" in html
    assert 'hx-get="/historial"' in html and 'hx-push-url="true"' in html


async def test_filtros_devuelven_solo_la_tabla(api, sesion_bd):
    http, _, (exitoso, fallido, revision), _ = await preparar(api, sesion_bd)
    por_estado = await htmx_get(http, "/historial", "pedidos", estado="FALLIDO")
    assert "<html" not in por_estado.text
    assert fallido in por_estado.text and exitoso not in por_estado.text

    por_player = await htmx_get(http, "/historial", "pedidos", player_id="11112222")
    assert fallido in por_player.text and revision not in por_player.text

    por_codigo = await htmx_get(http, "/historial", "pedidos", codigo=revision.lower())
    assert revision in por_codigo.text and exitoso not in por_codigo.text

    vacio = await htmx_get(http, "/historial", "pedidos", codigo="FF-999999999")
    assert "No hay pedidos con estos filtros." in vacio.text

    # Una restauración del historial del navegador recibe la página completa.
    completa = await http.get(
        "/historial",
        headers={
            "HX-Request": "true",
            "HX-Target": "pedidos",
            "HX-History-Restore-Request": "true",
        },
    )
    assert "<html" in completa.text


async def test_filtro_de_fechas_en_la_zona_del_usuario(api, sesion_bd):
    http, _, (exitoso, fallido, _), (id_exitoso, id_fallido) = await preparar(api, sesion_bd)
    # Exitoso: 2026-03-10 02:00 UTC = 9 de marzo 21:00 en UTC-5.
    # Fallido: 2026-03-10 06:00 UTC = 10 de marzo 01:00 en UTC-5.
    for pedido_id, fecha in (
        (id_exitoso, datetime(2026, 3, 10, 2, tzinfo=UTC)),
        (id_fallido, datetime(2026, 3, 10, 6, tzinfo=UTC)),
    ):
        await sesion_bd.execute(
            update(Pedido).where(Pedido.id == pedido_id).values(creado_en=fecha)
        )
    await sesion_bd.commit()

    # tz = 300 es lo que da getTimezoneOffset() en UTC-5.
    dia_9 = await htmx_get(
        http, "/historial", "pedidos", desde="2026-03-09", hasta="2026-03-09", tz="300"
    )
    assert exitoso in dia_9.text and fallido not in dia_9.text
    dia_10 = await htmx_get(
        http, "/historial", "pedidos", desde="2026-03-10", hasta="2026-03-10", tz="300"
    )
    assert fallido in dia_10.text and exitoso not in dia_10.text
    # Sin desfase (UTC) ambos son del 10 de marzo.
    utc = await htmx_get(http, "/historial", "pedidos", desde="2026-03-10", hasta="2026-03-10")
    assert exitoso in utc.text and fallido in utc.text
    assert '<time datetime="2026-03-10T02:00:00+00:00" data-local>' in utc.text

    invalida = await htmx_get(http, "/historial", "pedidos", desde="10/03/2026")
    assert invalida.status_code == 422 and "Fecha inválida" in invalida.text


async def test_paginacion(api, sesion_bd):
    http, usuario, paquete = await cliente_web(api, sesion_bd, abono=None)
    for _ in range(21):
        await pedido(sesion_bd, usuario, paquete, estado="EXITOSO")
    await sesion_bd.commit()
    primera = await http.get("/historial", params={"estado": "EXITOSO"})
    assert "página 1 de 2" in primera.text
    assert "/historial?estado=EXITOSO&amp;pagina=2" in primera.text
    segunda = await htmx_get(http, "/historial", "pedidos", estado="EXITOSO", pagina="2")
    assert "página 2 de 2" in segunda.text and segunda.text.count("<tr>") == 2


async def test_detalle_de_pedido_ajeno_es_404(api, sesion_bd):
    _, _, (exitoso, _, _), _ = await preparar(api, sesion_bd)
    otro = await crear_usuario_con_clave(sesion_bd)
    http = api()
    await iniciar_sesion(http, otro.usuario)
    ajeno = await http.get(f"/historial/{exitoso}")
    assert ajeno.status_code == 404 and "Pedido no encontrado." in ajeno.text
    assert exitoso not in (await http.get("/historial")).text
