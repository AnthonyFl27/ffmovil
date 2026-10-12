"""T-128: archivar y restaurar clientes (RF-60, RF-03, RF-04, RF-06, RF-07, RF-40, RF-41, RF-55, CA-11)."""

from decimal import Decimal

from sqlalchemy import func, select

from app.models import Movimiento, Pedido, Usuario
from app.services import ledger
from tests.test_admin_usuarios import acciones_auditadas, sesion_admin
from tests.utilidades import crear_paquete, crear_pedido
from tests.utilidades_api import crear_usuario_con_clave, iniciar_sesion


async def releer(sesion, usuario_id):
    return await sesion.get(Usuario, usuario_id, populate_existing=True)


async def ids_del_listado(c, **params):
    return {u["id"] for u in (await c.get("/admin/usuarios", params=params)).json()}


async def cliente_con_historial(sesion_bd, admin_id):
    """Cliente con un abono y un ajuste que lo dejan en cero y un pedido exitoso."""
    cliente = await crear_usuario_con_clave(sesion_bd)
    paquete = await crear_paquete(sesion_bd, precio_costo="0.50", precio_venta="0.75")
    await crear_pedido(sesion_bd, cliente.id, paquete, estado="EXITOSO")
    await ledger.abonar(sesion_bd, cliente.id, Decimal(5), nota="Yape", creado_por=admin_id)
    await ledger.ajustar(sesion_bd, cliente.id, Decimal(-5), nota="Cobro", creado_por=admin_id)
    await sesion_bd.commit()
    return cliente


async def test_archivar_con_saldo_cero_bloquea_oculta_y_conserva_el_historial(api, sesion_bd):
    c, admin_id = await sesion_admin(api, sesion_bd)
    cliente = await cliente_con_historial(sesion_bd, admin_id)
    sesion_cliente = api()
    await iniciar_sesion(sesion_cliente, cliente.usuario)

    respuesta = await c.post(f"/admin/usuarios/{cliente.id}/archivar")
    assert respuesta.status_code == 200
    assert (respuesta.json()["archivado"], respuesta.json()["activo"]) == (True, False)

    # RF-04 y RF-06: sin sesiones y sin poder entrar.
    assert (await sesion_cliente.get("/auth/sesion")).status_code == 401
    assert (await iniciar_sesion(api(), cliente.usuario)).status_code == 403
    # Fuera del listado normal; en el de archivados.
    assert cliente.id not in await ids_del_listado(c)
    assert cliente.id in await ids_del_listado(c, archivados="true")
    # Se conservan el historial de movimientos y los pedidos.
    historial = (await c.get(f"/admin/usuarios/{cliente.id}/movimientos")).json()
    assert historial["total"] == 2
    assert (
        await sesion_bd.scalar(
            select(func.count()).select_from(Pedido).where(Pedido.usuario_id == cliente.id)
        )
        == 1
    )
    assert (
        await sesion_bd.scalar(
            select(func.count()).select_from(Movimiento).where(Movimiento.usuario_id == cliente.id)
        )
        == 2
    )
    assert await acciones_auditadas(sesion_bd, admin_id) == [
        (
            "archivar_usuario",
            {"usuario_id": cliente.id, "usuario": cliente.usuario},
            "127.0.0.1",
        )
    ]


async def test_archivar_con_saldo_disponible_o_reservado_se_rechaza(api, sesion_bd):
    c, admin_id = await sesion_admin(api, sesion_bd)
    con_disponible = await crear_usuario_con_clave(sesion_bd)
    await ledger.abonar(
        sesion_bd, con_disponible.id, Decimal("5.00"), nota="Yape", creado_por=admin_id
    )
    con_reservado = await crear_usuario_con_clave(sesion_bd)
    paquete = await crear_paquete(sesion_bd, precio_costo="0.50", precio_venta="0.75")
    pedido = await crear_pedido(sesion_bd, con_reservado.id, paquete, estado="PROCESANDO")
    await ledger.abonar(
        sesion_bd, con_reservado.id, Decimal("0.75"), nota="Yape", creado_por=admin_id
    )
    await ledger.reservar(sesion_bd, con_reservado.id, Decimal("0.75"), pedido_id=pedido.id)
    await sesion_bd.commit()

    rechazo_disponible = await c.post(f"/admin/usuarios/{con_disponible.id}/archivar")
    rechazo_reservado = await c.post(f"/admin/usuarios/{con_reservado.id}/archivar")
    assert (rechazo_disponible.status_code, rechazo_reservado.status_code) == (409, 409)
    assert "disponible 5.00" in rechazo_disponible.json()["detail"]
    assert "reservado 0.75" in rechazo_reservado.json()["detail"]
    for cliente in (con_disponible, con_reservado):
        usuario = await releer(sesion_bd, cliente.id)
        assert (usuario.archivado, usuario.activo) == (False, True)
        assert cliente.id in await ids_del_listado(c)
    assert await acciones_auditadas(sesion_bd, admin_id) == []


async def test_archivar_admin_inexistente_y_estados_repetidos(api, sesion_bd):
    c, admin_id = await sesion_admin(api, sesion_bd)
    # Ni a uno mismo ni a otro admin.
    otro_admin = await crear_usuario_con_clave(sesion_bd, rol="admin")
    for objetivo in (admin_id, otro_admin.id):
        assert (await c.post(f"/admin/usuarios/{objetivo}/archivar")).status_code == 400
    for accion in ("archivar", "restaurar"):
        assert (await c.post(f"/admin/usuarios/999999999/{accion}")).status_code == 404

    cliente = await crear_usuario_con_clave(sesion_bd)
    assert (await c.post(f"/admin/usuarios/{cliente.id}/restaurar")).status_code == 409
    assert (await c.post(f"/admin/usuarios/{cliente.id}/archivar")).status_code == 200
    assert (await c.post(f"/admin/usuarios/{cliente.id}/archivar")).status_code == 409
    assert (await releer(sesion_bd, otro_admin.id)).archivado is False
    assert [a for a, _, _ in await acciones_auditadas(sesion_bd, admin_id)] == ["archivar_usuario"]


async def test_archivado_no_se_desbloquea_ni_recibe_abonos_ni_ajustes(api, sesion_bd):
    c, _ = await sesion_admin(api, sesion_bd)
    cliente = await crear_usuario_con_clave(sesion_bd)
    assert (await c.post(f"/admin/usuarios/{cliente.id}/archivar")).status_code == 200

    assert (await c.post(f"/admin/usuarios/{cliente.id}/desbloquear")).status_code == 409
    abono = await c.post(
        f"/admin/saldos/{cliente.id}/abono", json={"monto": "1.00", "nota": "Yape"}
    )
    ajuste = await c.post(
        f"/admin/saldos/{cliente.id}/ajuste", json={"monto": "1.00", "nota": "Error"}
    )
    assert (abono.status_code, ajuste.status_code) == (409, 409)
    usuario = await releer(sesion_bd, cliente.id)
    assert (usuario.archivado, usuario.activo) == (True, False)
    assert (
        await sesion_bd.scalar(
            select(func.count()).select_from(Movimiento).where(Movimiento.usuario_id == cliente.id)
        )
        == 0
    )


async def test_restaurar_vuelve_al_listado_y_sigue_bloqueado(api, sesion_bd):
    c, admin_id = await sesion_admin(api, sesion_bd)
    cliente = await crear_usuario_con_clave(sesion_bd)
    await c.post(f"/admin/usuarios/{cliente.id}/archivar")

    respuesta = await c.post(f"/admin/usuarios/{cliente.id}/restaurar")
    assert respuesta.status_code == 200
    assert (respuesta.json()["archivado"], respuesta.json()["activo"]) == (False, False)
    assert cliente.id in await ids_del_listado(c)
    assert cliente.id not in await ids_del_listado(c, archivados="true")
    assert (await iniciar_sesion(api(), cliente.usuario)).status_code == 403

    # Se desbloquea aparte y, ya sin archivar, vuelve a recibir abonos.
    assert (await c.post(f"/admin/usuarios/{cliente.id}/desbloquear")).status_code == 200
    assert (await iniciar_sesion(api(), cliente.usuario)).status_code == 200
    abono = await c.post(
        f"/admin/saldos/{cliente.id}/abono", json={"monto": "1.00", "nota": "Yape"}
    )
    assert abono.status_code == 201
    assert [a for a, _, _ in await acciones_auditadas(sesion_bd, admin_id)] == [
        "archivar_usuario",
        "restaurar_usuario",
        "desbloquear_usuario",
        "abono",
    ]


async def test_el_nombre_de_un_archivado_sigue_ocupado(api, sesion_bd):
    c, _ = await sesion_admin(api, sesion_bd)
    cliente = await crear_usuario_con_clave(sesion_bd)
    await c.post(f"/admin/usuarios/{cliente.id}/archivar")
    repetido = await c.post("/admin/usuarios", json={"usuario": cliente.usuario})
    assert repetido.status_code == 409
