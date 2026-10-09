"""T-073, T-106: Recargar en tres pasos (RF-20, RF-21, RF-25, CA-02; CHG-010).

Player ID → tarjeta del jugador y paquetes → resumen → confirmación.
"""

import re

from sqlalchemy import func, select

from app.models import Pedido
from tests.utilidades_web import cliente_web, htmx_post

PLAYER_ID = "75807448"


def campos_ocultos(html: str) -> dict:
    return dict(re.findall(r'<input type="hidden" name="(\w+)" value="([^"]*)">', html))


async def validar(http, player_id=PLAYER_ID):
    """Paso 2: tarjeta del jugador y paquetes."""
    return await htmx_post(http, "/recargar/validar", {"player_id": player_id})


async def resumen(http, paquete_id, html_paso2: str):
    """Paso 3: resumen del paquete elegido, con los campos ocultos del paso 2."""
    datos = campos_ocultos(html_paso2) | {"paquete_id": str(paquete_id)}
    return await htmx_post(http, "/recargar/resumen", datos)


async def confirmacion(http, paquete_id) -> dict:
    """Campos del formulario de confirmación tras los pasos 2 y 3."""
    paso2 = (await validar(http)).text
    return campos_ocultos((await resumen(http, paquete_id, paso2)).text)


async def pedidos_de(sesion, usuario_id) -> int:
    return await sesion.scalar(
        select(func.count()).select_from(Pedido).where(Pedido.usuario_id == usuario_id)
    )


async def test_pantalla_recargar_pide_solo_el_player_id(api, sesion_bd):
    http, _, _ = await cliente_web(api, sesion_bd)
    respuesta = await http.get("/recargar")
    assert respuesta.status_code == 200
    html = respuesta.text
    assert 'hx-post="/recargar/validar"' in html and 'hx-target="#recarga"' in html
    assert 'pattern="[0-9]{4,20}"' in html and "Saldo disponible" in html
    # Los paquetes aparecen recién tras verificar el ID (RF-20, CHG-010).
    assert 'name="paquete_id"' not in html


async def test_validar_muestra_tarjeta_del_jugador_y_paquetes(api, sesion_bd, simulador):
    http, usuario, paquete = await cliente_web(api, sesion_bd, simulador)
    respuesta = await validar(http)
    assert respuesta.status_code == 200
    html = respuesta.text
    assert "Nombre de usuario: Jugador7448" in html and f"ID de jugador: {PLAYER_ID}" in html
    assert '<span class="inicial" aria-hidden="true">J</span>' in html
    assert 'href="/recargar"' in html and "Cambiar ID" in html
    assert f'name="paquete_id" value="{paquete.paquete_id}"' in html and "0.75 USD" in html
    assert 'hx-post="/recargar/resumen" hx-trigger="change"' in html
    assert "Verificar ID" not in html and "token_idempotencia" not in html
    assert campos_ocultos(html) == {
        "player_id": PLAYER_ID,
        "nickname": "Jugador7448",
        "verificado": "1",
    }
    assert await pedidos_de(sesion_bd, usuario.id) == 0


async def test_resumen_con_token_y_confirmacion(api, sesion_bd, simulador):
    http, usuario, paquete = await cliente_web(api, sesion_bd, simulador)
    paso2 = (await validar(http)).text
    recargas_antes = len(simulador.recargas)
    respuesta = await resumen(http, paquete.paquete_id, paso2)
    assert respuesta.status_code == 200
    html = respuesta.text
    assert "Confirma la recarga" in html and "Jugador7448" in html and "0.75 USD" in html
    ocultos = campos_ocultos(html)
    assert ocultos["player_id"] == PLAYER_ID
    assert ocultos["paquete_id"] == str(paquete.paquete_id)
    assert re.fullmatch(r"[0-9a-f]{32}", ocultos["token_idempotencia"])
    # Botón deshabilitado tras el primer clic; el pedido reemplaza toda la pantalla.
    assert 'hx-post="/recargar/confirmar" hx-target="#recarga"' in html
    assert 'hx-disabled-elt="find button"' in html
    assert "confirmar_sin_verificar" not in html
    # Cada resumen genera un token nuevo y no llama a VentasFF.
    otro = campos_ocultos((await resumen(http, paquete.paquete_id, paso2)).text)
    assert otro["token_idempotencia"] != ocultos["token_idempotencia"]
    assert len(simulador.recargas) == recargas_antes
    assert await pedidos_de(sesion_bd, usuario.id) == 0


async def test_validar_rechazos_bajo_el_campo(api, sesion_bd, simulador):
    http, _, _ = await cliente_web(api, sesion_bd, simulador)
    formato = await validar(http, player_id="12a")
    assert formato.status_code == 422 and "de 4 a 20 dígitos" in formato.text
    assert formato.headers["HX-Retarget"] == "#mensaje-id"
    simulador.escenario_validar = "no_existe"
    no_existe = await validar(http)
    assert no_existe.status_code == 422 and "no existe" in no_existe.text
    assert no_existe.headers["HX-Retarget"] == "#mensaje-id"
    sin_paquete = await htmx_post(
        http, "/recargar/resumen", {"player_id": PLAYER_ID, "paquete_id": "x"}
    )
    assert sin_paquete.status_code == 422 and "Elige un paquete" in sin_paquete.text


async def test_recarga_exitosa(api, sesion_bd, simulador):
    http, usuario, paquete = await cliente_web(api, sesion_bd, simulador)
    ocultos = await confirmacion(http, paquete.paquete_id)

    respuesta = await htmx_post(http, "/recargar/confirmar", ocultos)
    assert respuesta.status_code == 200
    html = respuesta.text
    assert "Exitoso" in html and "estado-EXITOSO" in html
    assert "Jugador7448" in html and "0.75 USD" in html
    assert "hx-trigger" not in html  # estado final: no se consulta más
    assert len(simulador.recargas) == 1

    # CA-02: reenviar el mismo formulario (doble clic) no crea otro pedido.
    otra = await htmx_post(http, "/recargar/confirmar", ocultos)
    codigo = re.search(r"Pedido (FF-\d+)", html).group(1)
    assert f"Pedido {codigo}" in otra.text
    assert await pedidos_de(sesion_bd, usuario.id) == 1
    assert len(simulador.recargas) == 1


async def test_recarga_fallida_muestra_motivo(api, sesion_bd, simulador):
    http, _, paquete = await cliente_web(api, sesion_bd, simulador)
    simulador.escenario_recarga = "PURCHASE_FAILED"
    ocultos = await confirmacion(http, paquete.paquete_id)
    html = (await htmx_post(http, "/recargar/confirmar", ocultos)).text
    assert "Fallido" in html and "volvió a tu saldo" in html and "Motivo:" in html


async def test_id_sin_verificar_exige_confirmacion(api, sesion_bd, simulador):
    http, usuario, paquete = await cliente_web(api, sesion_bd, simulador)
    simulador.escenario_validar = "no_disponible"
    paso2 = (await validar(http)).text
    assert "No se pudo verificar el ID" in paso2 and "sin verificar" in paso2
    assert campos_ocultos(paso2)["verificado"] == ""
    html = (await resumen(http, paquete.paquete_id, paso2)).text
    assert 'name="confirmar_sin_verificar" value="1" required' in html

    ocultos = campos_ocultos(html)
    sin_marcar = await htmx_post(http, "/recargar/confirmar", ocultos)
    assert sin_marcar.status_code == 409
    assert sin_marcar.headers["HX-Retarget"] == "#mensaje-confirmacion"
    assert await pedidos_de(sesion_bd, usuario.id) == 0

    marcado = await htmx_post(
        http, "/recargar/confirmar", ocultos | {"confirmar_sin_verificar": "1"}
    )
    assert marcado.status_code == 200 and "Exitoso" in marcado.text


async def test_saldo_insuficiente(api, sesion_bd, simulador):
    http, usuario, paquete = await cliente_web(api, sesion_bd, simulador, abono=None)
    ocultos = await confirmacion(http, paquete.paquete_id)
    respuesta = await htmx_post(http, "/recargar/confirmar", ocultos)
    assert respuesta.status_code == 422 and "Saldo insuficiente" in respuesta.text
    assert await pedidos_de(sesion_bd, usuario.id) == 0


async def test_confirmar_sin_csrf_se_rechaza(api, sesion_bd, simulador):
    http, usuario, paquete = await cliente_web(api, sesion_bd, simulador)
    ocultos = await confirmacion(http, paquete.paquete_id)
    del http.headers["X-CSRF-Token"]
    respuesta = await htmx_post(http, "/recargar/confirmar", ocultos)
    assert respuesta.status_code == 403
    assert await pedidos_de(sesion_bd, usuario.id) == 0


async def test_pedido_en_proceso_se_consulta(api, sesion_bd, simulador):
    from tests.utilidades import crear_pedido

    http, usuario, paquete = await cliente_web(api, sesion_bd)
    pedido = await crear_pedido(sesion_bd, usuario.id, paquete, estado="PROCESANDO")
    from app.services.codigos import codigo_pedido

    pedido.codigo = codigo_pedido(pedido.id)
    await sesion_bd.commit()

    fragmento = await http.get(f"/historial/{pedido.codigo}", headers={"HX-Request": "true"})
    assert fragmento.status_code == 200
    assert f'hx-get="/historial/{pedido.codigo}"' in fragmento.text
    assert 'hx-trigger="every 3s"' in fragmento.text
    assert "<html" not in fragmento.text
    pagina = await http.get(f"/historial/{pedido.codigo}")
    assert "<html" in pagina.text and "Procesando" in pagina.text
