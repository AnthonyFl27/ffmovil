"""T-058: panel del admin, alertas y configuración (RF-53, RN-10, RN-11, RF-55)."""

from decimal import Decimal

from sqlalchemy import func, select

from app.models import Alerta, Auditoria, Saldo
from app.services import alertas
from app.services.ventasff_client import ClienteVentasFF
from tests.utilidades_api import crear_usuario_con_clave, iniciar_sesion


async def sesion_admin(api, sesion_bd):
    admin = await crear_usuario_con_clave(sesion_bd, rol="admin")
    c = api()
    await iniciar_sesion(c, admin.usuario)
    return c, admin.id


async def test_panel_compara_credito_con_saldos(api, sesion_bd, simulador):
    c, _ = await sesion_admin(api, sesion_bd)
    simulador.credito = Decimal("100000.00")
    suma = await sesion_bd.scalar(
        select(func.coalesce(func.sum(Saldo.saldo_disponible + Saldo.saldo_reservado), 0))
    )
    respuesta = await c.get("/admin/panel")
    assert respuesta.status_code == 200
    datos = respuesta.json()
    assert datos["credito_ventasff"] == "100000.00"
    assert datos["saldos_clientes"] == f"{suma:.2f}"
    assert datos["diferencia"] == f"{Decimal('100000.00') - suma:.2f}"
    assert datos["cubierto"] is True
    assert datos["saldo_por_cubrir"] == f"{max(suma - Decimal('100000.00'), Decimal(0)):.2f}"
    assert datos["error_proveedor"] is None
    assert datos["moneda"] == "USD"
    assert isinstance(datos["pendientes_verificar"], int)


async def test_panel_credito_insuficiente_y_bajo(api, sesion_bd, simulador):
    c, _ = await sesion_admin(api, sesion_bd)
    cliente = await crear_usuario_con_clave(sesion_bd)
    simulador.credito = Decimal("5.00")
    # RN-10: el abono se acepta aunque supere el crédito en VentasFF (pago adelantado).
    abono = await c.post(
        f"/admin/saldos/{cliente.id}/abono", json={"monto": "1000.00", "nota": "Adelanto"}
    )
    assert abono.status_code == 201
    datos = (await c.get("/admin/panel")).json()
    # El crédito no cubre los saldos: el saldo por cubrir es informativo, sin error.
    assert datos["cubierto"] is False
    assert Decimal(datos["diferencia"]) < 0
    assert Decimal(datos["saldo_por_cubrir"]) == -Decimal(datos["diferencia"])
    assert datos["error_proveedor"] is None
    # RN-11 (a): crédito por debajo del umbral → alerta activa de crédito bajo.
    assert "credito_bajo" in {a["tipo"] for a in datos["alertas"]}


async def test_panel_sin_respuesta_del_proveedor(api, sesion_bd, simulador):
    from app.main import app

    c, _ = await sesion_admin(api, sesion_bd)
    await app.state.ventasff.cerrar()
    app.state.ventasff = ClienteVentasFF(
        "clave_invalida", "http://simulador/api/reseller", transport=simulador.transporte()
    )
    datos = (await c.get("/admin/panel")).json()
    assert datos["credito_ventasff"] is None and datos["diferencia"] is None
    assert datos["saldo_por_cubrir"] is None
    assert datos["error_proveedor"]
    assert "clave_invalida" not in str(datos)


async def test_atender_alerta(api, sesion_bd):
    c, admin_id = await sesion_admin(api, sesion_bd)
    await alertas.registrar_alerta(sesion_bd, "cuenta", "Error de cuenta de prueba")
    await sesion_bd.commit()
    alerta_id = await sesion_bd.scalar(
        select(Alerta.id).where(Alerta.tipo == "cuenta", Alerta.atendida_en.is_(None))
    )
    assert alerta_id in {a["id"] for a in (await c.get("/admin/alertas")).json()}

    atendida = await c.post(f"/admin/alertas/{alerta_id}/atender")
    assert atendida.status_code == 200
    assert atendida.json()["atendida_por"] == admin_id
    assert alerta_id not in {a["id"] for a in (await c.get("/admin/alertas")).json()}
    assert (await c.post("/admin/alertas/999999999/atender")).status_code == 404
    acciones = (
        await sesion_bd.scalars(select(Auditoria.accion).where(Auditoria.usuario_id == admin_id))
    ).all()
    assert acciones == ["atender_alerta"]


async def test_config_umbral(api, sesion_bd):
    c, admin_id = await sesion_admin(api, sesion_bd)
    anterior = (await c.get("/admin/config")).json()["alerta_credito_min"]
    try:
        cambio = await c.put("/admin/config", json={"alerta_credito_min": "25.50"})
        assert cambio.status_code == 200
        assert (await c.get("/admin/config")).json() == {"alerta_credito_min": "25.50"}
        for invalido in ("-1", "1.001", "abc"):
            respuesta = await c.put("/admin/config", json={"alerta_credito_min": invalido})
            assert respuesta.status_code == 422
        detalle = await sesion_bd.scalar(
            select(Auditoria.detalle).where(
                Auditoria.usuario_id == admin_id, Auditoria.accion == "cambiar_config"
            )
        )
        assert detalle == {"clave": "alerta_credito_min", "anterior": anterior, "nuevo": "25.50"}
    finally:
        await c.put("/admin/config", json={"alerta_credito_min": anterior})
