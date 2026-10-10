"""T-109: historial de abonos y ajustes en la ficha del cliente (RF-43, RF-42, CHG-014, CHG-015)."""

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


async def test_lista_solo_abonos_y_ajustes_del_mas_reciente_al_mas_antiguo(api, sesion_bd):
    http, admin = await admin_con_sesion(api, sesion_bd)
    cliente, _ = await cliente_con_historial(sesion_bd, admin)

    r = await http.get(f"/admin/usuarios/{cliente.id}/movimientos")
    assert r.status_code == 200
    cuerpo = r.json()
    # La reserva y el cargo de la recarga no forman parte del historial (CHG-015).
    assert cuerpo["total"] == 2 and cuerpo["moneda"] == "USD"
    ajuste, abono = cuerpo["movimientos"]
    assert set(ajuste) == {"fecha", "tipo", "monto", "nota"}
    assert (ajuste["tipo"], ajuste["monto"], ajuste["nota"]) == ("ajuste", "-1.00", "Corrección")
    assert (abono["tipo"], abono["monto"], abono["nota"]) == ("abono", "10.00", "Pago móvil 1")


async def test_paginacion_y_filtros(api, sesion_bd):
    http, admin = await admin_con_sesion(api, sesion_bd)
    cliente, _ = await cliente_con_historial(sesion_bd, admin)
    ruta = f"/admin/usuarios/{cliente.id}/movimientos"

    pagina_1 = (await http.get(ruta, params={"por_pagina": 1})).json()
    pagina_2 = (await http.get(ruta, params={"por_pagina": 1, "pagina": 2})).json()
    assert pagina_1["total"] == 2 and [m["tipo"] for m in pagina_1["movimientos"]] == ["ajuste"]
    assert [m["tipo"] for m in pagina_2["movimientos"]] == ["abono"]

    solo_abonos = (await http.get(ruta, params={"tipo": "abono"})).json()
    assert [m["tipo"] for m in solo_abonos["movimientos"]] == ["abono"] and solo_abonos[
        "total"
    ] == 1
    # Reserva, liberación y cargo no son filtros válidos.
    for tipo in ("reserva", "liberacion", "cargo", "inventado"):
        assert (await http.get(ruta, params={"tipo": tipo})).status_code == 422

    ayer = (datetime.now(UTC) - timedelta(days=1)).isoformat()
    manana = (datetime.now(UTC) + timedelta(days=1)).isoformat()
    assert (await http.get(ruta, params={"desde": ayer, "hasta": manana})).json()["total"] == 2
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
    assert "Historial de abonos y ajustes" in pagina.text
    for esperado in ("Abono", "Ajuste", "10.00 USD", "-1.00 USD", "Pago móvil 1", "Corrección"):
        assert esperado in pagina.text
    # Sin reservas ni cargos, sin el pedido y sin columnas de autor o saldos resultantes.
    for ausente in ('data-etiqueta="Pedido"', 'data-etiqueta="Registrado por"', "Reserva</td>"):
        assert ausente not in pagina.text
    assert codigo not in pagina.text
    assert '<option value="reserva"' not in pagina.text

    # El filtro reemplaza solo la tabla (HTMX) y respeta el tipo.
    parcial = await htmx_get(
        http, f"/gestion/usuarios/{cliente.id}", destino="movimientos", tipo="abono"
    )
    assert parcial.status_code == 200
    assert "<html" not in parcial.text and "Pago móvil 1" in parcial.text
    assert "Corrección" not in parcial.text

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
    assert "Efectivo" in abono.text and "4.00 USD" in abono.text


async def test_ficha_de_admin_no_tiene_historial(api, sesion_bd):
    http, admin = await admin_con_sesion(api, sesion_bd)
    pagina = await http.get(f"/gestion/usuarios/{admin.id}")
    assert pagina.status_code == 200 and "Historial de abonos y ajustes" not in pagina.text
    assert (await http.get("/gestion/usuarios/999999999")).status_code == 404
