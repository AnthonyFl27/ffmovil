"""T-059: catálogo del admin: precio de venta, activación, sincronizar y bajo costo (RF-10 a RF-14)."""

import random
from decimal import Decimal

from sqlalchemy import select

from app.models import Auditoria, Paquete
from tests.utilidades import crear_paquete
from tests.utilidades_api import crear_usuario_con_clave, iniciar_sesion


async def sesion_admin(api, sesion_bd):
    admin = await crear_usuario_con_clave(sesion_bd, rol="admin")
    c = api()
    await iniciar_sesion(c, admin.usuario)
    return c, admin.id


async def test_fijar_precio_activar_y_desactivar(api, sesion_bd):
    c, admin_id = await sesion_admin(api, sesion_bd)
    paquete = await crear_paquete(sesion_bd, precio_costo="0.50", precio_venta=None, activo=False)
    await sesion_bd.commit()
    ruta = f"/admin/paquetes/{paquete.paquete_id}"

    # RF-11: sin precio no se activa.
    sin_precio = await c.put(ruta, json={"activo": True})
    assert sin_precio.status_code == 422

    # RF-12: aviso si precio_venta <= precio_costo.
    bajo = await c.put(ruta, json={"precio_venta": "0.50"})
    assert bajo.status_code == 200
    assert (bajo.json()["precio_venta"], bajo.json()["bajo_costo"]) == ("0.50", True)

    activado = await c.put(ruta, json={"precio_venta": "0.75", "activo": True})
    assert activado.status_code == 200
    datos = activado.json()
    assert (datos["precio_venta"], datos["activo"], datos["bajo_costo"]) == ("0.75", True, False)
    assert datos["precio_costo"] == "0.50"

    desactivado = await c.put(ruta, json={"activo": False})
    assert desactivado.json()["activo"] is False

    for cuerpo in ({"precio_venta": "0"}, {"precio_venta": "-1"}, {"precio_venta": "1.234"}):
        assert (await c.put(ruta, json=cuerpo)).status_code == 422
    inexistente = await c.put("/admin/paquetes/1999999999", json={"activo": False})
    assert inexistente.status_code == 404

    detalles = (
        await sesion_bd.scalars(
            select(Auditoria.detalle)
            .where(Auditoria.usuario_id == admin_id, Auditoria.accion == "editar_paquete")
            .order_by(Auditoria.id)
        )
    ).all()
    assert detalles == [
        {"paquete_id": paquete.paquete_id, "precio_anterior": None, "precio_venta": "0.50"},
        {
            "paquete_id": paquete.paquete_id,
            "precio_anterior": "0.50",
            "precio_venta": "0.75",
            "activo": True,
        },
        {"paquete_id": paquete.paquete_id, "activo": False},
    ]


async def test_listado_marca_bajo_costo(api, sesion_bd):
    c, _ = await sesion_admin(api, sesion_bd)
    bajo = await crear_paquete(sesion_bd, precio_costo="0.80", precio_venta="0.70")
    normal = await crear_paquete(sesion_bd, precio_costo="0.50", precio_venta="0.75")
    await sesion_bd.commit()
    datos = (await c.get("/admin/paquetes")).json()
    por_id = {p["paquete_id"]: p for p in datos["paquetes"]}
    assert por_id[bajo.paquete_id]["bajo_costo"] is True
    assert por_id[normal.paquete_id]["bajo_costo"] is False
    assert por_id[normal.paquete_id]["precio_costo"] == "0.50"


async def test_sincronizar_ahora(api, sesion_bd, simulador):
    c, admin_id = await sesion_admin(api, sesion_bd)
    nuevo_id = random.randint(1_000_000_000, 2_000_000_000)
    simulador.productos = [
        {
            "paquete_id": nuevo_id,
            "nombre": "Paquete simulado",
            "juego": "free_fire",
            "diamantes": 100,
            "precio": Decimal("0.60"),
            "currency": "USD",
            "dato_extra": None,
        }
    ]
    respuesta = await c.post("/admin/catalogo/sincronizar")
    assert respuesta.status_code == 200
    datos = respuesta.json()
    nuevo = next(p for p in datos["paquetes"] if p["paquete_id"] == nuevo_id)
    # RF-10: los nuevos llegan inactivos y sin precio de venta.
    assert (nuevo["activo"], nuevo["precio_venta"], nuevo["precio_costo"]) == (False, None, "0.60")
    assert datos["ultima_sincronizacion"]["resultado"] == "ok"
    acciones = (
        await sesion_bd.scalars(select(Auditoria.accion).where(Auditoria.usuario_id == admin_id))
    ).all()
    assert acciones == ["sincronizar_catalogo"]


async def test_sincronizar_con_proveedor_caido(api, sesion_bd, simulador):
    from app.main import app
    from app.services.ventasff_client import ClienteVentasFF

    c, _ = await sesion_admin(api, sesion_bd)
    app.state.crear_cliente_ventasff = lambda: ClienteVentasFF(
        "clave_invalida", "http://simulador/api/reseller", transport=simulador.transporte()
    )
    antes = (await sesion_bd.scalars(select(Paquete.paquete_id).where(Paquete.activo))).all()
    respuesta = await c.post("/admin/catalogo/sincronizar")
    assert respuesta.status_code == 502
    despues = (
        await sesion_bd.scalars(
            select(Paquete.paquete_id)
            .where(Paquete.activo)
            .execution_options(populate_existing=True)
        )
    ).all()
    assert sorted(despues) == sorted(antes)
