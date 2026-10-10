"""T-054: /paquetes, /recargas/validar y /recargas (RF-13, RF-20 a RF-27, CA-02)."""

import asyncio
import uuid
from decimal import Decimal

from sqlalchemy import func, select

from app.models import Pedido
from app.routers import recargas
from app.services import ledger
from tests.utilidades import crear_paquete
from tests.utilidades_api import crear_usuario_con_clave, iniciar_sesion

PLAYER_ID = "75807448"


async def preparar(sesion, simulador, api, *, abono="10.00"):
    """Cliente con saldo y un paquete activo que el simulador conoce. Devuelve (http, paquete, id)."""
    usuario = await crear_usuario_con_clave(sesion)
    admin = await crear_usuario_con_clave(sesion, rol="admin")
    paquete = await crear_paquete(sesion, precio_costo="0.50", precio_venta="0.75")
    if abono:
        await ledger.abonar(sesion, usuario.id, Decimal(abono), nota="Abono", creado_por=admin.id)
    await sesion.commit()
    simulador.productos[0]["paquete_id"] = paquete.paquete_id
    simulador.productos[0]["precio"] = Decimal("0.50")
    c = api()
    await iniciar_sesion(c, usuario.usuario)
    return c, paquete.paquete_id, usuario.id


def solicitud(paquete_id, **cambios):
    return {
        "paquete_id": paquete_id,
        "player_id": PLAYER_ID,
        "token_idempotencia": uuid.uuid4().hex,
    } | cambios


async def test_paquetes_solo_activos_con_precio(api, sesion_bd):
    activo = await crear_paquete(sesion_bd, precio_costo="0.50", precio_venta="0.75")
    inactivo = await crear_paquete(sesion_bd, activo=False)
    sin_precio = await crear_paquete(sesion_bd, precio_venta=None, activo=False)
    usuario = await crear_usuario_con_clave(sesion_bd)
    c = api()
    await iniciar_sesion(c, usuario.usuario)
    respuesta = await c.get("/paquetes")
    assert respuesta.status_code == 200
    assert "costo" not in respuesta.text  # RF-35, CA-03
    por_id = {p["paquete_id"]: p for p in respuesta.json()}
    assert por_id[activo.paquete_id] == {
        "paquete_id": activo.paquete_id,
        "nombre": "110 Diamantes",
        "diamantes": 110,
        "precio_venta": "0.75",
    }
    assert inactivo.paquete_id not in por_id and sin_precio.paquete_id not in por_id


async def test_validar(api, sesion_bd, simulador):
    c, paquete_id, _ = await preparar(sesion_bd, simulador, api, abono=None)
    ok = await c.post("/recargas/validar", json={"player_id": PLAYER_ID, "paquete_id": paquete_id})
    assert ok.status_code == 200
    assert ok.json() == {"estado": "ok", "nickname": "Jugador7448", "advertencia": None}

    simulador.escenario_validar = "no_disponible"
    aviso = await c.post(
        "/recargas/validar", json={"player_id": PLAYER_ID, "paquete_id": paquete_id}
    )
    assert aviso.json()["estado"] == "no_disponible" and aviso.json()["advertencia"]

    simulador.escenario_validar = "no_existe"
    no_existe = await c.post(
        "/recargas/validar", json={"player_id": PLAYER_ID, "paquete_id": paquete_id}
    )
    formato = await c.post("/recargas/validar", json={"player_id": "12a", "paquete_id": paquete_id})
    assert no_existe.status_code == formato.status_code == 422
    assert "no existe" in no_existe.json()["detail"]


async def test_recarga_exitosa_e_idempotente(api, sesion_bd, simulador):
    c, paquete_id, _ = await preparar(sesion_bd, simulador, api)
    datos = solicitud(paquete_id)
    primera = await c.post("/recargas", json=datos)
    assert primera.status_code == 201
    pedido = primera.json()
    assert (pedido["estado"], pedido["estado_etiqueta"]) == ("EXITOSO", "Exitoso")
    assert pedido["referencia"].startswith("EV-")
    assert (pedido["monto"], pedido["nickname"]) == ("0.75", "Jugador7448")
    assert "costo" not in primera.text

    # CA-02: el reenvío con el mismo token devuelve el mismo pedido sin recargar otra vez.
    segunda = await c.post("/recargas", json=datos)
    assert segunda.status_code == 200
    assert segunda.json()["codigo"] == pedido["codigo"]
    assert len(simulador.recargas) == 1
    resumen = (await c.get("/me/resumen")).json()
    assert (resumen["saldo_disponible"], resumen["recargas"]) == ("9.25", 1)


async def test_recarga_fallida_libera_el_saldo(api, sesion_bd, simulador):
    c, paquete_id, _ = await preparar(sesion_bd, simulador, api)
    simulador.escenario_recarga = "PURCHASE_FAILED"
    respuesta = await c.post("/recargas", json=solicitud(paquete_id))
    assert respuesta.status_code == 201
    pedido = respuesta.json()
    assert (pedido["estado"], pedido["motivo"]) == ("FALLIDO", "Paquete no disponible")
    assert (await c.get("/me/resumen")).json()["saldo_disponible"] == "10.00"


async def test_recarga_incierta_queda_en_revision(api, sesion_bd, simulador):
    c, paquete_id, _ = await preparar(sesion_bd, simulador, api)
    simulador.escenario_recarga = "timeout"
    pedido = (await c.post("/recargas", json=solicitud(paquete_id))).json()
    assert (pedido["estado"], pedido["estado_etiqueta"]) == ("PENDIENTE_VERIFICAR", "En revisión")
    resumen = (await c.get("/me/resumen")).json()
    assert (resumen["saldo_disponible"], resumen["saldo_reservado"]) == ("9.25", "0.75")


async def test_id_no_verificado_requiere_confirmacion(api, sesion_bd, simulador):
    c, paquete_id, _ = await preparar(sesion_bd, simulador, api)
    simulador.escenario_validar = "no_disponible"
    sin_confirmar = await c.post("/recargas", json=solicitud(paquete_id))
    assert sin_confirmar.status_code == 409
    assert sin_confirmar.json()["detail"]
    confirmada = await c.post("/recargas", json=solicitud(paquete_id, confirmar_sin_verificar=True))
    assert confirmada.status_code == 201
    assert confirmada.json()["estado"] == "EXITOSO"
    assert confirmada.json()["nickname"] is None


async def test_rechazos_sin_crear_pedido(api, sesion_bd, simulador):
    """RN-03: con el ID inexistente en la revalidación no se crea pedido ni se llama a recargar."""
    c, paquete_id, usuario_id = await preparar(sesion_bd, simulador, api, abono="0.50")
    saldo = await c.post("/recargas", json=solicitud(paquete_id))
    assert saldo.status_code == 422 and "Saldo insuficiente" in saldo.json()["detail"]
    simulador.escenario_validar = "no_existe"
    no_existe = await c.post("/recargas", json=solicitud(paquete_id))
    assert no_existe.status_code == 422
    sin_token = await c.post("/recargas", json=solicitud(paquete_id, token_idempotencia=" "))
    assert sin_token.status_code == 422
    cantidad = await sesion_bd.scalar(
        select(func.count()).select_from(Pedido).where(Pedido.usuario_id == usuario_id)
    )
    assert cantidad == 0
    assert simulador.recargas == []


async def test_la_recarga_sigue_si_la_respuesta_no_espera(api, sesion_bd, simulador, monkeypatch):
    from app.main import app

    c, paquete_id, _ = await preparar(sesion_bd, simulador, api)
    # Sin espera: la ruta responde con el pedido en proceso y la tarea sigue sola.
    monkeypatch.setattr(recargas, "ESPERA_RESULTADO_SEGUNDOS", 0)
    respuesta = await c.post("/recargas", json=solicitud(paquete_id))
    assert respuesta.status_code == 201
    assert respuesta.json()["estado_etiqueta"] == "Procesando"
    await asyncio.wait(set(app.state.tareas_recarga), timeout=30)
    detalle = await c.get(f"/me/pedidos/{respuesta.json()['codigo']}")
    assert detalle.json()["estado"] == "EXITOSO"
    assert not app.state.tareas_recarga


async def test_recargas_exige_cliente(api, sesion_bd):
    admin = await crear_usuario_con_clave(sesion_bd, rol="admin")
    c = api()
    assert (await c.get("/paquetes")).status_code == 401
    await iniciar_sesion(c, admin.usuario)
    assert (await c.post("/recargas", json=solicitud(1))).status_code == 403
