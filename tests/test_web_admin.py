"""T-076: pantallas admin: usuarios, abonos, pedidos, resolución, panel y configuración.

RF-03, RF-12, RF-40, RF-41, RF-50 a RF-55, RN-10, RN-11.
"""

import re
import uuid
from decimal import Decimal

from sqlalchemy import select

from app.models import Alerta, Auditoria, Paquete, Pedido, Saldo, Usuario
from app.services import ledger
from app.services.codigos import codigo_pedido
from tests.utilidades import crear_paquete, crear_pedido
from tests.utilidades_api import crear_usuario_con_clave, iniciar_sesion
from tests.utilidades_web import HTMX, htmx_get, htmx_post


async def admin_web(api, sesion):
    admin = await crear_usuario_con_clave(sesion, rol="admin")
    http = api()
    await iniciar_sesion(http, admin.usuario)
    return http, admin


async def releer(sesion, modelo, clave):
    return await sesion.get(modelo, clave, populate_existing=True)


async def test_cliente_no_entra_a_gestion(api, sesion_bd):
    cliente = await crear_usuario_con_clave(sesion_bd)
    http = api()
    await iniciar_sesion(http, cliente.usuario)
    for ruta in ("/gestion", "/gestion/usuarios", "/gestion/pedidos", "/gestion/config"):
        respuesta = await http.get(ruta)
        assert (respuesta.status_code, respuesta.headers["location"]) == (303, "/inicio")
    # Una acción por HTMX también se rechaza (redirección, sin efecto).
    respuesta = await htmx_post(http, "/gestion/usuarios", {"usuario": "intruso_web"})
    assert respuesta.headers["HX-Redirect"] == "/inicio"
    assert await sesion_bd.scalar(select(Usuario).where(Usuario.usuario == "intruso_web")) is None


async def test_panel_con_credito_saldos_y_alertas(api, sesion_bd, simulador):
    http, _ = await admin_web(api, sesion_bd)
    simulador.credito = Decimal("1000000.00")
    respuesta = await http.get("/gestion")
    assert respuesta.status_code == 200
    html = respuesta.text
    assert '<strong id="credito-ventasff">1000000.00 USD</strong>' in html
    assert 'id="saldos-clientes"' in html and 'id="ganancia-total"' in html
    assert 'href="/gestion/pedidos?solo_pendientes=1"' in html


async def test_atender_alerta(api, sesion_bd):
    http, _ = await admin_web(api, sesion_bd)
    from app.services import alertas

    await alertas.registrar_alerta(sesion_bd, "cuenta", "Error de cuenta de prueba")
    await sesion_bd.commit()
    alerta = await sesion_bd.scalar(
        select(Alerta).where(Alerta.tipo == "cuenta", Alerta.atendida_en.is_(None))
    )
    respuesta = await htmx_post(http, f"/gestion/alertas/{alerta.id}/atender")
    assert respuesta.status_code == 200
    assert f"/gestion/alertas/{alerta.id}/atender" not in respuesta.text
    assert (await releer(sesion_bd, Alerta, alerta.id)).atendida_en is not None
    inexistente = await htmx_post(http, "/gestion/alertas/999999999/atender")
    assert inexistente.status_code == 404 and "Alerta no encontrada." in inexistente.text


async def test_usuarios_crear_bloquear_y_resetear(api, sesion_bd):
    http, _ = await admin_web(api, sesion_bd)
    assert 'hx-post="/gestion/usuarios"' in (await http.get("/gestion/usuarios")).text

    nombre = f"web_{uuid.uuid4().hex[:10]}"
    creado = await htmx_post(http, "/gestion/usuarios", {"usuario": nombre})
    assert creado.status_code == 200
    clave = re.search(r'<code id="clave-temporal">([^<]+)</code>', creado.text).group(1)
    assert 'hx-swap-oob="true"' in creado.text and nombre in creado.text
    usuario = await sesion_bd.scalar(select(Usuario).where(Usuario.usuario == nombre))
    assert usuario.debe_cambiar_clave and usuario.rol == "cliente"

    duplicado = await htmx_post(http, "/gestion/usuarios", {"usuario": nombre})
    invalido = await htmx_post(http, "/gestion/usuarios", {"usuario": "a"})
    assert (duplicado.status_code, invalido.status_code) == (409, 422)

    pagina = await http.get(f"/gestion/usuarios/{usuario.id}")
    assert pagina.status_code == 200 and f"/gestion/usuarios/{usuario.id}/bloquear" in pagina.text

    bloqueado = await htmx_post(http, f"/gestion/usuarios/{usuario.id}/bloquear")
    assert "Bloqueado" in bloqueado.text and "/desbloquear" in bloqueado.text
    assert (await releer(sesion_bd, Usuario, usuario.id)).activo is False
    await htmx_post(http, f"/gestion/usuarios/{usuario.id}/desbloquear")
    assert (await releer(sesion_bd, Usuario, usuario.id)).activo is True

    reseteo = await htmx_post(http, f"/gestion/usuarios/{usuario.id}/reset-clave")
    nueva = re.search(r'<code id="clave-temporal">([^<]+)</code>', reseteo.text).group(1)
    assert nueva != clave

    acciones = await sesion_bd.scalars(
        select(Auditoria.accion).where(Auditoria.detalle["usuario_id"].as_integer() == usuario.id)
    )
    assert set(acciones) >= {"crear_usuario", "bloquear_usuario", "resetear_clave"}
    assert (await http.get("/gestion/usuarios/999999999")).status_code == 404


async def test_no_puede_bloquearse_a_si_mismo(api, sesion_bd):
    http, admin = await admin_web(api, sesion_bd)
    respuesta = await htmx_post(http, f"/gestion/usuarios/{admin.id}/bloquear")
    assert respuesta.status_code == 400 and "No puedes bloquear" in respuesta.text


async def test_abono_y_ajuste(api, sesion_bd):
    http, _ = await admin_web(api, sesion_bd)
    cliente = await crear_usuario_con_clave(sesion_bd)
    ruta = f"/gestion/usuarios/{cliente.id}/saldo"

    abono = await htmx_post(http, f"{ruta}/abono", {"monto": "12.50", "nota": "Pago móvil 123"})
    assert abono.status_code == 200
    assert "Abono de 12.50 USD registrado" in abono.text
    assert '<strong id="saldo-disponible">12.50 USD</strong>' in abono.text

    ajuste = await htmx_post(http, f"{ruta}/ajuste", {"monto": "-2.50", "nota": "Corrección"})
    assert "Ajuste de -2.50 USD registrado" in ajuste.text
    saldo = await releer(sesion_bd, Saldo, cliente.id)
    assert saldo.saldo_disponible == Decimal("10.00")

    for datos, tipo in (
        ({"monto": "abc", "nota": "x"}, "abono"),
        ({"monto": "5", "nota": ""}, "abono"),
        ({"monto": "-50", "nota": "Deja negativo"}, "ajuste"),
    ):
        rechazo = await htmx_post(http, f"{ruta}/{tipo}", datos)
        assert rechazo.status_code == 422 and 'class="mensaje error"' in rechazo.text
    assert (await releer(sesion_bd, Saldo, cliente.id)).saldo_disponible == Decimal("10.00")


async def test_pedidos_filtros_y_resolucion(api, sesion_bd):
    http, admin = await admin_web(api, sesion_bd)
    cliente = await crear_usuario_con_clave(sesion_bd)
    paquete = await crear_paquete(sesion_bd, precio_costo="0.50", precio_venta="0.75")
    await ledger.abonar(sesion_bd, cliente.id, Decimal("5.00"), nota="Abono", creado_por=admin.id)
    await ledger.reservar(sesion_bd, cliente.id, Decimal("0.75"))
    pendiente = await crear_pedido(
        sesion_bd, cliente.id, paquete, estado="PENDIENTE_VERIFICAR", player_id="55556666"
    )
    exitoso = await crear_pedido(
        sesion_bd, cliente.id, paquete, estado="EXITOSO", referencia="EV-WEB0001"
    )
    pendiente.codigo, exitoso.codigo = codigo_pedido(pendiente.id), codigo_pedido(exitoso.id)
    await sesion_bd.commit()

    pagina = await http.get("/gestion/pedidos", params={"usuario": cliente.usuario})
    assert pagina.status_code == 200
    assert pendiente.codigo in pagina.text and exitoso.codigo in pagina.text
    # Totales del filtro (RF-54): una venta exitosa de 0.75 con costo 0.50.
    assert "0.25 USD" in pagina.text

    por_referencia = await htmx_get(http, "/gestion/pedidos", "pedidos", referencia="EV-WEB0001")
    assert exitoso.codigo in por_referencia.text and pendiente.codigo not in por_referencia.text
    assert "<html" not in por_referencia.text
    solo = await htmx_get(
        http, "/gestion/pedidos", "pedidos", usuario=cliente.usuario, solo_pendientes="1"
    )
    assert pendiente.codigo in solo.text and exitoso.codigo not in solo.text

    detalle = await http.get(f"/gestion/pedidos/{pendiente.codigo}")
    assert detalle.status_code == 200 and "0.50 USD" in detalle.text
    assert f'hx-post="/gestion/pedidos/{pendiente.id}/resolver"' in detalle.text

    sin_resultado = await htmx_post(
        http, f"/gestion/pedidos/{pendiente.id}/resolver", {"nota": "x"}
    )
    assert sin_resultado.status_code == 422
    assert sin_resultado.headers["HX-Retarget"] == "#mensaje-resolucion"

    resuelto = await htmx_post(
        http,
        f"/gestion/pedidos/{pendiente.id}/resolver",
        {"resultado": "exitoso", "referencia": "EV-MANUAL1", "nota": "Verificado en VentasFF"},
    )
    assert resuelto.status_code == 200 and "EV-MANUAL1" in resuelto.text
    assert 'hx-post="/gestion/pedidos/' not in resuelto.text
    assert (await releer(sesion_bd, Pedido, pendiente.id)).estado == "EXITOSO"
    assert (await releer(sesion_bd, Saldo, cliente.id)).saldo_reservado == Decimal("0.00")

    otra_vez = await htmx_post(
        http,
        f"/gestion/pedidos/{pendiente.id}/resolver",
        {"resultado": "fallido", "nota": "Repetido"},
    )
    assert otra_vez.status_code == 409
    assert (await http.get("/gestion/pedidos/FF-999999999")).status_code == 404


async def test_catalogo_precio_activar_y_sincronizar(api, sesion_bd, simulador):
    http, _ = await admin_web(api, sesion_bd)
    paquete = await crear_paquete(sesion_bd, precio_costo="0.50", precio_venta=None, activo=False)
    await sesion_bd.commit()
    pagina = await http.get("/gestion/paquetes")
    assert f'id="paquete-{paquete.paquete_id}"' in pagina.text

    ruta = f"/gestion/paquetes/{paquete.paquete_id}"
    sin_precio = await htmx_post(http, ruta, {"activo": "si"})
    assert sin_precio.status_code == 422
    assert sin_precio.headers["HX-Retarget"] == "#mensaje-catalogo"

    bajo = await htmx_post(http, ruta, {"precio_venta": "0.40"})
    assert bajo.status_code == 200 and "(bajo costo)" in bajo.text
    assert bajo.text.lstrip().startswith(f'<tr id="paquete-{paquete.paquete_id}"')
    await htmx_post(http, ruta, {"precio_venta": "0.75"})
    activo = await htmx_post(http, ruta, {"activo": "si"})
    assert "Desactivar" in activo.text
    guardado = await releer(sesion_bd, Paquete, paquete.paquete_id)
    assert (guardado.precio_venta, guardado.activo) == (Decimal("0.75"), True)
    invalido = await htmx_post(http, ruta, {"precio_venta": "barato"})
    assert invalido.status_code == 422

    sincronizado = await htmx_post(http, "/gestion/catalogo/sincronizar")
    assert sincronizado.status_code == 200 and "Catálogo sincronizado." in sincronizado.text


async def test_configuracion_del_umbral(api, sesion_bd):
    http, _ = await admin_web(api, sesion_bd)
    pagina = await http.get("/gestion/config")
    assert 'name="alerta_credito_min"' in pagina.text
    guardar = await htmx_post(http, "/gestion/config", {"alerta_credito_min": "15.00"})
    assert guardar.status_code == 200 and "guardado" in guardar.text
    assert 'value="15.00"' in (await http.get("/gestion/config")).text
    invalido = await htmx_post(http, "/gestion/config", {"alerta_credito_min": "-1"})
    assert invalido.status_code == 422
    # Deja el valor inicial para las demás pruebas (RN-11).
    await htmx_post(http, "/gestion/config", {"alerta_credito_min": "10.00"})


async def test_auditoria(api, sesion_bd):
    http, _ = await admin_web(api, sesion_bd)
    await htmx_post(http, "/gestion/config", {"alerta_credito_min": "10.00"})
    pagina = await http.get("/gestion/auditoria", params={"accion": "cambiar_config"})
    assert pagina.status_code == 200 and "cambiar_config" in pagina.text
    parcial = await http.get(
        "/gestion/auditoria",
        params={"accion": "no_existe"},
        headers=HTMX | {"HX-Target": "registros"},
    )
    assert "No hay registros." in parcial.text and "<html" not in parcial.text
