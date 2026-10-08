"""T-060: cada acción del admin que cambia datos registra una fila de auditoría (RF-55)."""

from decimal import Decimal

from sqlalchemy import select

from app.main import app
from app.models import Alerta
from app.services import alertas, ledger
from app.services.codigos import codigo_pedido
from tests.utilidades import crear_paquete, crear_pedido
from tests.utilidades_api import crear_usuario_con_clave, iniciar_sesion

# Rutas admin que cambian datos y la acción que registran.
ACCIONES = {
    ("POST", "/admin/usuarios"): "crear_usuario",
    ("POST", "/admin/usuarios/{usuario_id}/bloquear"): "bloquear_usuario",
    ("POST", "/admin/usuarios/{usuario_id}/desbloquear"): "desbloquear_usuario",
    ("POST", "/admin/usuarios/{usuario_id}/reset-clave"): "resetear_clave",
    ("POST", "/admin/saldos/{usuario_id}/abono"): "abono",
    ("POST", "/admin/saldos/{usuario_id}/ajuste"): "ajuste",
    ("POST", "/admin/pedidos/{pedido}/resolver"): "resolver_pedido",
    ("POST", "/admin/alertas/{alerta_id}/atender"): "atender_alerta",
    ("PUT", "/admin/config"): "cambiar_config",
    ("PUT", "/admin/paquetes/{paquete_id}"): "editar_paquete",
    ("POST", "/admin/catalogo/sincronizar"): "sincronizar_catalogo",
}


def test_todas_las_rutas_admin_que_cambian_datos_estan_cubiertas():
    """Una ruta admin nueva que cambie datos debe añadirse aquí (y auditarse)."""
    mutables = {
        (metodo.upper(), ruta)
        for ruta, metodos in app.openapi()["paths"].items()
        if ruta.startswith("/admin")
        for metodo in metodos
        if metodo.upper() != "GET"
    }
    assert mutables == set(ACCIONES)


async def test_cada_accion_registra_una_fila(api, sesion_bd):
    admin = await crear_usuario_con_clave(sesion_bd, rol="admin")
    cliente = await crear_usuario_con_clave(sesion_bd)
    paquete = await crear_paquete(sesion_bd, precio_costo="0.50", precio_venta="0.75")
    pedido = await crear_pedido(sesion_bd, cliente.id, paquete, estado="PENDIENTE_VERIFICAR")
    pedido.codigo = codigo_pedido(pedido.id)
    await ledger.abonar(sesion_bd, cliente.id, Decimal(5), nota="Inicial", creado_por=admin.id)
    await ledger.reservar(sesion_bd, cliente.id, Decimal("0.75"), pedido_id=pedido.id)
    await alertas.registrar_alerta(sesion_bd, "sin_credito", "Alerta de prueba")
    await sesion_bd.commit()
    alerta_id = await sesion_bd.scalar(
        select(Alerta.id).where(Alerta.tipo == "sin_credito", Alerta.atendida_en.is_(None))
    )
    c = api()
    await iniciar_sesion(c, admin.usuario)
    umbral = (await c.get("/admin/config")).json()["alerta_credito_min"]

    llamadas = [
        c.post("/admin/usuarios", json={"usuario": f"audit_{cliente.id}"}),
        c.post(f"/admin/usuarios/{cliente.id}/bloquear"),
        c.post(f"/admin/usuarios/{cliente.id}/desbloquear"),
        c.post(f"/admin/usuarios/{cliente.id}/reset-clave"),
        c.post(f"/admin/saldos/{cliente.id}/abono", json={"monto": "1", "nota": "Yape"}),
        c.post(f"/admin/saldos/{cliente.id}/ajuste", json={"monto": "-1", "nota": "Error"}),
        c.post(
            f"/admin/pedidos/{pedido.id}/resolver",
            json={"resultado": "fallido", "nota": "No llegó"},
        ),
        c.post(f"/admin/alertas/{alerta_id}/atender"),
        c.put("/admin/config", json={"alerta_credito_min": umbral}),
        c.put(f"/admin/paquetes/{paquete.paquete_id}", json={"precio_venta": "0.80"}),
        c.post("/admin/catalogo/sincronizar"),
    ]
    for llamada in llamadas:
        respuesta = await llamada
        assert respuesta.status_code in (200, 201), respuesta.text

    registro = (await c.get("/admin/auditoria", params={"usuario_id": admin.id})).json()
    assert registro["total"] == len(ACCIONES)
    acciones = [r["accion"] for r in reversed(registro["registros"])]
    assert acciones == list(ACCIONES.values())
    assert all(
        r["usuario"] == admin.usuario and r["ip"] == "127.0.0.1" for r in registro["registros"]
    )

    filtrado = await c.get("/admin/auditoria", params={"usuario_id": admin.id, "accion": "abono"})
    assert filtrado.json()["total"] == 1
    assert filtrado.json()["registros"][0]["detalle"]["nota"] == "Yape"
