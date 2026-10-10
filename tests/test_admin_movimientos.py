"""T-109: historial de movimientos de saldo en la ficha del cliente (RF-43, RF-42, CHG-014)."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from app.services import ledger
from app.services.codigos import codigo_pedido
from tests.utilidades import crear_paquete, crear_pedido
from tests.utilidades_api import crear_usuario_con_clave, iniciar_sesion
from tests.utilidades_web import htmx_get, htmx_post


async def admin_con_sesion(api, sesion_bd):
    admin = await crear_usuario_con_clave(sesion_bd, rol="admin")
    http = api()
    await iniciar_sesion(http, admin.usuario)
    return http, admin


async def cliente_con_historial(sesion_bd, admin):
    """Abono 10.00, ajuste -1.00 y una recarga cobrada de 0.75 (reserva + cargo)."""
    cliente = await crear_usuario_con_clave(sesion_bd)
    paquete = await crear_paquete(sesion_bd, precio_costo="0.50", precio_venta="0.75")
    pedido = await crear_pedido(sesion_bd, cliente.id, paquete)
    pedido.codigo = codigo_pedido(pedido.id)
    await ledger.abonar(
        sesion_bd, cliente.id, Decimal("10.00"), nota="Pago móvil 1", creado_por=admin.id
    )
    await ledger.ajustar(
        sesion_bd, cliente.id, Decimal("-1.00"), nota="Corrección", creado_por=admin.id
    )
    await ledger.reservar(sesion_bd, cliente.id, Decimal("0.75"), pedido_id=pedido.id)
    await ledger.cargar(sesion_bd, cliente.id, Decimal("0.75"), pedido_id=pedido.id)
    codigo = pedido.codigo
    await sesion_bd.commit()
    return cliente, codigo


async def test_lista_del_mas_reciente_al_mas_antiguo(api, sesion_bd):
    http, admin = await admin_con_sesion(api, sesion_bd)
    cliente, codigo = await cliente_con_historial(sesion_bd, admin)

    r = await http.get(f"/admin/usuarios/{cliente.id}/movimientos")
    assert r.status_code == 200
    cuerpo = r.json()
    assert cuerpo["total"] == 4 and cuerpo["moneda"] == "USD"
    movimientos = cuerpo["movimientos"]
    assert [m["tipo"] for m in movimientos] == ["cargo", "reserva", "ajuste", "abono"]

    cargo, reserva, ajuste, abono = movimientos
    # Reserva y cargo salen de la cuenta: se muestran en negativo.
    assert cargo["monto"] == "-0.75" and reserva["monto"] == "-0.75"
    assert ajuste["monto"] == "-1.00" and abono["monto"] == "10.00"
    assert cargo["pedido_codigo"] == codigo and reserva["pedido_codigo"] == codigo
    assert abono["pedido_id"] is None and abono["pedido_codigo"] is None
    assert abono["nota"] == "Pago móvil 1" and ajuste["nota"] == "Corrección"
    # El admin registra abonos y ajustes; las recargas las genera el sistema.
    assert abono["registrado_por"] == admin.usuario == ajuste["registrado_por"]
    assert reserva["registrado_por"] == "sistema" == cargo["registrado_por"]
    # Saldos resultantes: tras el abono y el ajuste 9.00; la reserva pasa 0.75 a reservado.
    assert abono["saldo_disponible_resultante"] == "10.00"
    assert reserva["saldo_disponible_resultante"] == "8.25"
    assert reserva["saldo_reservado_resultante"] == "0.75"
    assert cargo["saldo_reservado_resultante"] == "0.00"


async def test_paginacion_y_filtros(api, sesion_bd):
    http, admin = await admin_con_sesion(api, sesion_bd)
    cliente, _ = await cliente_con_historial(sesion_bd, admin)
    ruta = f"/admin/usuarios/{cliente.id}/movimientos"

    pagina_1 = (await http.get(ruta, params={"por_pagina": 3})).json()
    pagina_2 = (await http.get(ruta, params={"por_pagina": 3, "pagina": 2})).json()
    assert pagina_1["total"] == 4 and len(pagina_1["movimientos"]) == 3
    assert [m["tipo"] for m in pagina_2["movimientos"]] == ["abono"]

    solo_abonos = (await http.get(ruta, params={"tipo": "abono"})).json()
    assert [m["tipo"] for m in solo_abonos["movimientos"]] == ["abono"] and solo_abonos[
        "total"
    ] == 1
    assert (await http.get(ruta, params={"tipo": "inventado"})).status_code == 422

    ayer = (datetime.now(UTC) - timedelta(days=1)).isoformat()
    manana = (datetime.now(UTC) + timedelta(days=1)).isoformat()
    assert (await http.get(ruta, params={"desde": ayer, "hasta": manana})).json()["total"] == 4
    assert (await http.get(ruta, params={"desde": manana})).json()["total"] == 0
    assert (await http.get(ruta, params={"hasta": ayer})).json()["total"] == 0


async def test_solo_los_movimientos_del_usuario_consultado(api, sesion_bd):
    http, admin = await admin_con_sesion(api, sesion_bd)
    cliente, _ = await cliente_con_historial(sesion_bd, admin)
    otro = await crear_usuario_con_clave(sesion_bd)
    await ledger.abonar(
        sesion_bd, otro.id, Decimal("5.00"), nota="Otro cliente", creado_por=admin.id
    )
    await sesion_bd.commit()

    notas = {
        m["nota"]
        for m in (await http.get(f"/admin/usuarios/{cliente.id}/movimientos")).json()["movimientos"]
    }
    assert "Otro cliente" not in notas
    propios = (await http.get(f"/admin/usuarios/{otro.id}/movimientos")).json()
    assert propios["total"] == 1 and propios["movimientos"][0]["nota"] == "Otro cliente"


async def test_usuario_inexistente_y_permisos(api, sesion_bd):
    http, _ = await admin_con_sesion(api, sesion_bd)
    assert (await http.get("/admin/usuarios/999999999/movimientos")).status_code == 404

    cliente = await crear_usuario_con_clave(sesion_bd)
    c = api()
    await iniciar_sesion(c, cliente.usuario)
    assert (await c.get(f"/admin/usuarios/{cliente.id}/movimientos")).status_code == 403
    assert (await api().get(f"/admin/usuarios/{cliente.id}/movimientos")).status_code == 401


async def test_la_consulta_no_escribe_en_el_libro(api, sesion_bd):
    http, admin = await admin_con_sesion(api, sesion_bd)
    cliente, _ = await cliente_con_historial(sesion_bd, admin)
    ruta = f"/admin/usuarios/{cliente.id}/movimientos"
    antes = (await http.get(ruta)).json()
    despues = (await http.get(ruta)).json()
    assert antes == despues


async def test_ficha_web_muestra_el_historial(api, sesion_bd):
    http, admin = await admin_con_sesion(api, sesion_bd)
    cliente, codigo = await cliente_con_historial(sesion_bd, admin)

    pagina = await http.get(f"/gestion/usuarios/{cliente.id}")
    assert pagina.status_code == 200
    assert "Historial de movimientos" in pagina.text
    for esperado in (
        "Abono",
        "Ajuste",
        "Reserva",
        "Cargo",
        "+10.00 USD",
        "-1.00 USD",
        "Pago móvil 1",
    ):
        assert esperado in pagina.text
    assert 'href="/gestion/pedidos/' in pagina.text and codigo in pagina.text
    assert "sistema" in pagina.text and admin.usuario in pagina.text

    # El filtro reemplaza solo la tabla (HTMX) y respeta el tipo.
    parcial = await htmx_get(
        http, f"/gestion/usuarios/{cliente.id}", destino="movimientos", tipo="abono"
    )
    assert parcial.status_code == 200
    assert "<html" not in parcial.text and "Pago móvil 1" in parcial.text
    assert "Corrección" not in parcial.text
    assert '<td data-etiqueta="Tipo">Reserva</td>' not in parcial.text
    assert '<td data-etiqueta="Tipo">Abono</td>' in parcial.text

    vacio = await htmx_get(
        http, f"/gestion/usuarios/{cliente.id}", destino="movimientos", desde="2999-01-01"
    )
    assert "No hay movimientos con estos filtros." in vacio.text


async def test_ficha_web_se_actualiza_tras_un_abono(api, sesion_bd):
    http, _ = await admin_con_sesion(api, sesion_bd)
    cliente = await crear_usuario_con_clave(sesion_bd)

    antes = await http.get(f"/gestion/usuarios/{cliente.id}")
    assert "No hay movimientos con estos filtros." in antes.text

    abono = await htmx_post(
        http, f"/gestion/usuarios/{cliente.id}/saldo/abono", {"monto": "4.00", "nota": "Efectivo"}
    )
    assert abono.status_code == 200
    assert 'id="movimientos" hx-swap-oob="true"' in abono.text
    assert "Efectivo" in abono.text and "+4.00 USD" in abono.text


async def test_ficha_de_admin_no_tiene_historial(api, sesion_bd):
    http, admin = await admin_con_sesion(api, sesion_bd)
    pagina = await http.get(f"/gestion/usuarios/{admin.id}")
    assert pagina.status_code == 200 and "Historial de movimientos" not in pagina.text
    assert (await http.get("/gestion/usuarios/999999999")).status_code == 404
