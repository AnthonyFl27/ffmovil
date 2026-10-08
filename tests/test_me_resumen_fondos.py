"""T-052: /me/resumen y /me/fondos (RF-33, RF-34, RF-36)."""

from decimal import Decimal

from app.services import ledger
from tests.utilidades import crear_paquete, crear_pedido
from tests.utilidades_api import crear_usuario_con_clave, iniciar_sesion


async def preparar_cliente(sesion, admin_id):
    """Cliente con un abono, un ajuste y pedidos exitoso, fallido y pendiente."""
    usuario = await crear_usuario_con_clave(sesion)
    paquete = await crear_paquete(sesion, precio_costo="0.50", precio_venta="0.75")
    await ledger.abonar(sesion, usuario.id, Decimal(50), nota="Yape ref 123", creado_por=admin_id)
    await ledger.ajustar(sesion, usuario.id, Decimal(-5), nota="Corrección", creado_por=admin_id)
    for estado in ("EXITOSO", "FALLIDO", "PENDIENTE_VERIFICAR"):
        pedido = await crear_pedido(sesion, usuario.id, paquete, estado=estado)
        await ledger.reservar(sesion, usuario.id, paquete.precio_venta, pedido_id=pedido.id)
        if estado == "EXITOSO":
            await ledger.cargar(sesion, usuario.id, paquete.precio_venta, pedido_id=pedido.id)
        elif estado == "FALLIDO":
            await ledger.liberar(sesion, usuario.id, paquete.precio_venta, pedido_id=pedido.id)
    await sesion.commit()
    return usuario


async def test_resumen_cuenta_solo_exitosos(api, sesion_bd, admin_id):
    usuario = await preparar_cliente(sesion_bd, admin_id)
    c = api()
    await iniciar_sesion(c, usuario.usuario)
    respuesta = await c.get("/me/resumen")
    assert respuesta.status_code == 200
    assert respuesta.json() == {
        "saldo_disponible": "43.50",
        "saldo_reservado": "0.75",
        "gasto_total": "0.75",
        "recargas": 1,
        "moneda": "USD",
    }


async def test_resumen_cliente_sin_pedidos(api, sesion_bd):
    usuario = await crear_usuario_con_clave(sesion_bd)
    c = api()
    await iniciar_sesion(c, usuario.usuario)
    datos = (await c.get("/me/resumen")).json()
    assert (datos["saldo_disponible"], datos["gasto_total"], datos["recargas"]) == (
        "0.00",
        "0.00",
        0,
    )


async def test_fondos_muestra_abonos_y_ajustes(api, sesion_bd, admin_id):
    usuario = await preparar_cliente(sesion_bd, admin_id)
    c = api()
    await iniciar_sesion(c, usuario.usuario)
    datos = (await c.get("/me/fondos")).json()
    assert (datos["saldo_disponible"], datos["saldo_reservado"], datos["moneda"]) == (
        "43.50",
        "0.75",
        "USD",
    )
    # Solo abonos y ajustes (no reservas ni cargos), los más recientes primero.
    assert [(m["tipo"], m["monto"], m["nota"]) for m in datos["movimientos"]] == [
        ("ajuste", "-5.00", "Corrección"),
        ("abono", "50.00", "Yape ref 123"),
    ]
    assert datos["movimientos"][0]["fecha"]


async def test_me_exige_sesion_de_cliente(api, sesion_bd):
    admin = await crear_usuario_con_clave(sesion_bd, rol="admin")
    c = api()
    assert (await c.get("/me/resumen")).status_code == 401
    await iniciar_sesion(c, admin.usuario)
    assert (await c.get("/me/resumen")).status_code == 403
    assert (await c.get("/me/fondos")).status_code == 403
