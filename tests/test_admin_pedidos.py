"""T-057: pedidos del admin con filtros, detalle con costo y ganancia, y resolución (RF-50 a RF-52, RF-54, CA-06)."""

import random
import uuid
from datetime import UTC, datetime
from decimal import Decimal

from app.models import PedidoEvento
from app.services import ledger
from app.services.codigos import codigo_pedido
from app.services.recarga_service import MENSAJE_FALLIDO_POR_ADMIN
from tests.utilidades import crear_paquete, crear_pedido
from tests.utilidades_api import crear_usuario_con_clave, iniciar_sesion


def _referencia() -> str:
    return f"EV-{uuid.uuid4().hex[:8].upper()}"


def _player_id() -> str:
    return str(random.randint(10**9, 10**10))


async def pedir_pedidos(sesion):
    """Cliente con cuatro pedidos: dos EXITOSO en días distintos, un FALLIDO y un PENDIENTE_VERIFICAR.

    Devuelve el nombre de usuario, el paquete y los datos de cada pedido por clave.
    """
    cliente = await crear_usuario_con_clave(sesion)
    nombre = cliente.usuario
    paquete = await crear_paquete(sesion, precio_costo="0.50", precio_venta="0.75")
    especificaciones = {
        "exitoso_reciente": {
            "estado": "EXITOSO",
            "creado_en": datetime(2026, 10, 4, 12, tzinfo=UTC),
            "referencia": _referencia(),
        },
        "exitoso_antiguo": {
            "estado": "EXITOSO",
            "creado_en": datetime(2026, 10, 1, 12, tzinfo=UTC),
            "referencia": _referencia(),
        },
        "fallido": {
            "estado": "FALLIDO",
            "creado_en": datetime(2026, 10, 3, 12, tzinfo=UTC),
            "error": "Motivo X",
            "error_code": "PURCHASE_FAILED",
            "player_id": _player_id(),
        },
        "pendiente": {
            "estado": "PENDIENTE_VERIFICAR",
            "creado_en": datetime(2026, 10, 2, 12, tzinfo=UTC),
            "player_id": _player_id(),
        },
    }
    pedidos = {}
    for clave, extra in especificaciones.items():
        pedido = await crear_pedido(sesion, cliente.id, paquete, **extra)
        pedido.codigo = codigo_pedido(pedido.id)
        pedidos[clave] = {
            "id": pedido.id,
            "codigo": pedido.codigo,
            "referencia": pedido.referencia,
            "player_id": pedido.player_id,
        }
    await sesion.commit()
    return nombre, paquete, pedidos


async def crear_pendiente(sesion, cliente_id, paquete, admin_id):
    """Pedido PENDIENTE_VERIFICAR con su monto reservado (RN-04). Devuelve id y código."""
    pedido = await crear_pedido(sesion, cliente_id, paquete, estado="PENDIENTE_VERIFICAR")
    pedido.codigo = codigo_pedido(pedido.id)
    await ledger.reservar(sesion, cliente_id, Decimal("0.75"), pedido_id=pedido.id)
    return {"id": pedido.id, "codigo": pedido.codigo}


async def admin_conectado(api, sesion):
    admin = await crear_usuario_con_clave(sesion, rol="admin")
    c = api()
    await iniciar_sesion(c, admin.usuario)
    return c, admin.id


async def test_listado_y_totales(api, sesion_bd):
    nombre, _, pedidos = await pedir_pedidos(sesion_bd)
    c, _ = await admin_conectado(api, sesion_bd)

    respuesta = await c.get("/admin/pedidos", params={"usuario": nombre.upper()})
    assert respuesta.status_code == 200
    datos = respuesta.json()
    assert datos["total"] == 4
    assert datos["totales"] == {
        "exitosos": 2,
        "venta": "1.50",
        "costo": "1.00",
        "ganancia": "0.50",
    }
    # Más reciente primero.
    assert datos["pedidos"][0]["codigo"] == pedidos["exitoso_reciente"]["codigo"]
    assert {p["codigo"] for p in datos["pedidos"]} == {p["codigo"] for p in pedidos.values()}
    for pedido in datos["pedidos"]:
        assert pedido["usuario"] == nombre
        assert pedido["paquete"] == "110 Diamantes"
        assert (pedido["precio_costo"], pedido["precio_venta"]) == ("0.50", "0.75")
        esperada = "0.25" if pedido["estado"] == "EXITOSO" else None
        assert pedido["ganancia"] == esperada

    # RF-54: los totales siguen el rango de fechas; desde es inclusivo.
    respuesta = await c.get(
        "/admin/pedidos", params={"usuario": nombre, "desde": "2026-10-02T00:00:00Z"}
    )
    datos = respuesta.json()
    assert datos["total"] == 3
    assert datos["totales"] == {
        "exitosos": 1,
        "venta": "0.75",
        "costo": "0.50",
        "ganancia": "0.25",
    }


async def test_localizar_pedido(api, sesion_bd):
    nombre, _, pedidos = await pedir_pedidos(sesion_bd)
    c, _ = await admin_conectado(api, sesion_bd)

    async def consultar(**params):
        datos = (await c.get("/admin/pedidos", params=params)).json()
        return datos["total"], [p["codigo"] for p in datos["pedidos"]]

    exitoso = pedidos["exitoso_reciente"]
    fallido = pedidos["fallido"]
    pendiente = pedidos["pendiente"]
    assert await consultar(codigo=exitoso["codigo"]) == (1, [exitoso["codigo"]])
    assert await consultar(referencia=exitoso["referencia"]) == (1, [exitoso["codigo"]])
    assert await consultar(player_id=fallido["player_id"]) == (1, [fallido["codigo"]])
    assert await consultar(usuario=nombre, solo_pendientes="true") == (
        1,
        [pendiente["codigo"]],
    )
    assert await consultar(usuario=nombre, estado="FALLIDO") == (1, [fallido["codigo"]])


async def test_detalle_por_id_y_codigo(api, sesion_bd):
    nombre, _, pedidos = await pedir_pedidos(sesion_bd)
    exitoso = pedidos["exitoso_reciente"]
    sesion_bd.add(
        PedidoEvento(
            pedido_id=exitoso["id"],
            estado_anterior="PROCESANDO",
            estado_nuevo="EXITOSO",
            detalle="Referencia X",
        )
    )
    await sesion_bd.commit()
    c, _ = await admin_conectado(api, sesion_bd)

    por_id = await c.get(f"/admin/pedidos/{exitoso['id']}")
    por_codigo = await c.get(f"/admin/pedidos/{exitoso['codigo']}")
    assert por_id.status_code == por_codigo.status_code == 200
    datos = por_id.json()
    assert datos == por_codigo.json()
    assert (datos["codigo"], datos["usuario"], datos["ganancia"]) == (
        exitoso["codigo"],
        nombre,
        "0.25",
    )
    assert [(e["estado_anterior"], e["estado_nuevo"], e["detalle"]) for e in datos["eventos"]] == [
        ("PROCESANDO", "EXITOSO", "Referencia X")
    ]

    pendiente = pedidos["pendiente"]
    detalle_pendiente = (await c.get(f"/admin/pedidos/{pendiente['codigo']}")).json()
    assert detalle_pendiente["ganancia"] is None

    for pedido in ("999999999", "nada"):
        assert (await c.get(f"/admin/pedidos/{pedido}")).status_code == 404


async def test_resolucion_manual(api, sesion_bd):
    admin = await crear_usuario_con_clave(sesion_bd, rol="admin")
    admin_id = admin.id
    cliente = await crear_usuario_con_clave(sesion_bd)
    paquete = await crear_paquete(sesion_bd, precio_costo="0.50", precio_venta="0.75")
    await ledger.abonar(sesion_bd, cliente.id, Decimal(5), nota="x", creado_por=admin_id)
    exito = await crear_pendiente(sesion_bd, cliente.id, paquete, admin_id)
    fallo = await crear_pendiente(sesion_bd, cliente.id, paquete, admin_id)
    validacion = await crear_pendiente(sesion_bd, cliente.id, paquete, admin_id)
    await sesion_bd.commit()

    c = api()
    await iniciar_sesion(c, admin.usuario)
    referencia = _referencia()

    # Cuerpos inválidos: no cambian el pedido.
    sin_nota = {"resultado": "exitoso", "nota": "  "}
    otro_resultado = {"resultado": "otro", "nota": "Revisado"}
    assert (
        await c.post(f"/admin/pedidos/{validacion['id']}/resolver", json=sin_nota)
    ).status_code == 422
    assert (
        await c.post(f"/admin/pedidos/{validacion['id']}/resolver", json=otro_resultado)
    ).status_code == 422
    assert (
        await c.post(
            "/admin/pedidos/999999999/resolver",
            json={"resultado": "exitoso", "nota": "No existe"},
        )
    ).status_code == 404

    # RF-52: exitoso con nota y referencia; cobra la reserva (ganancia 0.25).
    respuesta = await c.post(
        f"/admin/pedidos/{exito['id']}/resolver",
        json={
            "resultado": "exitoso",
            "nota": "Verificado en panel",
            "referencia": referencia,
        },
    )
    assert respuesta.status_code == 200
    datos = respuesta.json()
    assert (datos["estado"], datos["referencia"], datos["ganancia"]) == (
        "EXITOSO",
        referencia,
        "0.25",
    )
    assert datos["eventos"][-1]["creado_por"] == admin_id

    # Ya resuelto: no se vuelve a resolver.
    repetida = await c.post(
        f"/admin/pedidos/{exito['id']}/resolver",
        json={"resultado": "fallido", "nota": "Otra vez"},
    )
    assert repetida.status_code == 409

    # Fallido: libera la reserva y usa el mensaje fijo para el cliente.
    respuesta = await c.post(
        f"/admin/pedidos/{fallo['id']}/resolver",
        json={"resultado": "fallido", "nota": "No llegó la recarga"},
    )
    assert respuesta.status_code == 200
    datos = respuesta.json()
    assert datos["estado"] == "FALLIDO"
    assert datos["error"] == MENSAJE_FALLIDO_POR_ADMIN
    assert datos["ganancia"] is None


async def test_solo_admin(api, sesion_bd):
    _, _, pedidos = await pedir_pedidos(sesion_bd)
    pendiente = pedidos["pendiente"]
    cliente = await crear_usuario_con_clave(sesion_bd)
    await sesion_bd.commit()

    c = api()
    await iniciar_sesion(c, cliente.usuario)
    assert (await c.get("/admin/pedidos")).status_code == 403
    assert (await c.get(f"/admin/pedidos/{pendiente['id']}")).status_code == 403
    assert (
        await c.post(
            f"/admin/pedidos/{pendiente['id']}/resolver",
            json={"resultado": "exitoso", "nota": "Intento de cliente"},
        )
    ).status_code == 403

    anonimo = api()
    assert (await anonimo.get("/admin/pedidos")).status_code == 401
    assert (await anonimo.get(f"/admin/pedidos/{pendiente['id']}")).status_code == 401
