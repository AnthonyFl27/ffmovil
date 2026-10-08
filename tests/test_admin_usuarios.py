"""T-055: el admin crea clientes, bloquea, desbloquea y resetea claves (RF-03, RF-06, RF-55)."""

import uuid

from sqlalchemy import select

from app.models import Auditoria
from tests.utilidades_api import crear_usuario_con_clave, iniciar_sesion


async def sesion_admin(api, sesion_bd):
    admin = await crear_usuario_con_clave(sesion_bd, rol="admin")
    c = api()
    await iniciar_sesion(c, admin.usuario)
    return c, admin.id


async def acciones_auditadas(sesion_bd, admin_id):
    filas = await sesion_bd.execute(
        select(Auditoria.accion, Auditoria.detalle, Auditoria.ip)
        .where(Auditoria.usuario_id == admin_id)
        .order_by(Auditoria.id)
    )
    return [(accion, detalle, str(ip)) for accion, detalle, ip in filas]


async def test_crear_cliente_con_clave_temporal(api, sesion_bd):
    c, admin_id = await sesion_admin(api, sesion_bd)
    nombre = f"Cli.{uuid.uuid4().hex[:8]}"
    respuesta = await c.post("/admin/usuarios", json={"usuario": f" {nombre} "})
    assert respuesta.status_code == 201
    datos = respuesta.json()
    usuario = datos["usuario"]
    # RF-07: se guarda en minúsculas; RF-03: solo clientes, con saldo en cero.
    assert usuario["usuario"] == nombre.lower()
    assert (usuario["rol"], usuario["activo"], usuario["debe_cambiar_clave"]) == (
        "cliente",
        True,
        True,
    )
    assert (usuario["saldo_disponible"], usuario["saldo_reservado"]) == ("0.00", "0.00")

    # El cliente entra con la clave temporal y debe cambiarla (RF-02).
    login = await iniciar_sesion(api(), nombre, datos["clave_temporal"])
    assert login.status_code == 200 and login.json()["debe_cambiar_clave"] is True

    duplicado = await c.post("/admin/usuarios", json={"usuario": nombre})
    invalido = await c.post("/admin/usuarios", json={"usuario": "con espacio"})
    assert (duplicado.status_code, invalido.status_code) == (409, 422)

    listado = (await c.get("/admin/usuarios")).json()
    assert any(u["id"] == usuario["id"] for u in listado)

    auditadas = await acciones_auditadas(sesion_bd, admin_id)
    assert auditadas == [
        (
            "crear_usuario",
            {"usuario_id": usuario["id"], "usuario": nombre.lower()},
            "127.0.0.1",
        )
    ]
    assert datos["clave_temporal"] not in str(auditadas)


async def test_bloquear_cierra_sesiones_y_desbloquear(api, sesion_bd):
    c, admin_id = await sesion_admin(api, sesion_bd)
    cliente = await crear_usuario_con_clave(sesion_bd)
    sesion_cliente = api()
    await iniciar_sesion(sesion_cliente, cliente.usuario)

    bloqueo = await c.post(f"/admin/usuarios/{cliente.id}/bloquear")
    assert bloqueo.status_code == 200 and bloqueo.json()["activo"] is False
    assert (await sesion_cliente.get("/auth/sesion")).status_code == 401
    assert (await iniciar_sesion(api(), cliente.usuario)).status_code == 403

    desbloqueo = await c.post(f"/admin/usuarios/{cliente.id}/desbloquear")
    assert desbloqueo.json()["activo"] is True
    assert (await iniciar_sesion(api(), cliente.usuario)).status_code == 200

    assert [a for a, _, _ in await acciones_auditadas(sesion_bd, admin_id)] == [
        "bloquear_usuario",
        "desbloquear_usuario",
    ]


async def test_resetear_clave(api, sesion_bd):
    c, admin_id = await sesion_admin(api, sesion_bd)
    cliente = await crear_usuario_con_clave(sesion_bd)
    sesion_cliente = api()
    await iniciar_sesion(sesion_cliente, cliente.usuario)

    respuesta = await c.post(f"/admin/usuarios/{cliente.id}/reset-clave")
    assert respuesta.status_code == 200
    temporal = respuesta.json()["clave_temporal"]
    assert respuesta.json()["usuario"]["debe_cambiar_clave"] is True
    assert (await sesion_cliente.get("/auth/sesion")).status_code == 401
    assert (await iniciar_sesion(api(), cliente.usuario)).status_code == 401
    login = await iniciar_sesion(api(), cliente.usuario, temporal)
    assert login.status_code == 200 and login.json()["debe_cambiar_clave"] is True

    auditadas = await acciones_auditadas(sesion_bd, admin_id)
    assert [a for a, _, _ in auditadas] == ["resetear_clave"]
    assert temporal not in str(auditadas)


async def test_no_puede_bloquearse_a_si_mismo_ni_a_inexistentes(api, sesion_bd):
    c, admin_id = await sesion_admin(api, sesion_bd)
    propio = await c.post(f"/admin/usuarios/{admin_id}/bloquear")
    assert propio.status_code == 400
    assert (await c.get("/auth/sesion")).status_code == 200
    for accion in ("bloquear", "desbloquear", "reset-clave"):
        assert (await c.post(f"/admin/usuarios/999999999/{accion}")).status_code == 404
    assert await acciones_auditadas(sesion_bd, admin_id) == []
