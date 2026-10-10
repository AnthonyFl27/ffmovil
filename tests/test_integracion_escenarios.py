"""T-080: integración completa por escenario del simulador de VentasFF.

Cada escenario recorre la app por HTTP, de punta a punta: el admin abona, el cliente
recarga, y se comprueban a la vez el pedido, la contabilidad, lo que ve el cliente
(API y páginas), lo que ve el admin (detalle, listado, panel y alertas) y lo que
hizo el proveedor. Las pruebas por capa (fases A/B/C, alertas, clasificación) están
en sus propios archivos; aquí se verifica que todas las piezas encajan.

RF-22 a RF-25, RF-30, RF-31, RF-35, RF-51, RF-52, RN-02, RN-04, RN-06, RN-08, RN-11, CA-02 a CA-05.
"""

import uuid
from dataclasses import dataclass
from decimal import Decimal

import pytest
from sqlalchemy import func, select, update

from app.models import Alerta, Movimiento, Saldo
from app.services.recarga_service import (
    MENSAJE_PROVEEDOR_OCUPADO,
    MENSAJE_SERVICIO_NO_DISPONIBLE,
    MENSAJE_SIN_CONEXION,
    MENSAJE_SIN_DISPONIBILIDAD,
)
from tests.fake_ventasff import ESCENARIOS_RECARGA
from tests.test_invariante_contable import suma_por_tipo
from tests.utilidades import crear_paquete
from tests.utilidades_api import crear_usuario_con_clave, iniciar_sesion

PLAYER_ID = "75807448"
D = Decimal
ABONO = "10.00"
VENTA, COSTO, GANANCIA = "0.75", "0.50", "0.25"


@dataclass(frozen=True)
class Caso:
    """Resultado esperado de una recarga de 0.75 con 10.00 de saldo, por escenario."""

    estado: str
    etiqueta: str
    disponible: str
    reservado: str
    movimientos: tuple[str, ...]
    motivo: str | None = None
    codigo_error: str | None = None
    alerta: str | None = None
    cobra_el_proveedor: bool = False


EXITO = {
    "estado": "EXITOSO",
    "etiqueta": "Exitoso",
    "disponible": "9.25",
    "reservado": "0.00",
    "movimientos": ("reserva", "cargo"),
    "cobra_el_proveedor": True,
}
RETENIDO = {
    "estado": "PENDIENTE_VERIFICAR",
    "etiqueta": "En revisión",
    "disponible": "9.25",
    "reservado": "0.75",
    "movimientos": ("reserva",),
    "cobra_el_proveedor": True,
}
LIBERADO = {
    "estado": "FALLIDO",
    "etiqueta": "Fallido",
    "disponible": "10.00",
    "reservado": "0.00",
    "movimientos": ("reserva", "liberacion"),
}

CASOS = {
    "ok": Caso(**EXITO),
    "nickname_null": Caso(**EXITO),
    "PURCHASE_FAILED": Caso(
        **LIBERADO, motivo="Paquete no disponible", codigo_error="PURCHASE_FAILED"
    ),
    "BUSY": Caso(**LIBERADO, motivo=MENSAJE_PROVEEDOR_OCUPADO, codigo_error="BUSY"),
    "INSUFFICIENT_CREDIT": Caso(
        **LIBERADO,
        motivo=MENSAJE_SIN_DISPONIBILIDAD,
        codigo_error="INSUFFICIENT_CREDIT",
        alerta="sin_credito",
    ),
    "INVALID_KEY": Caso(
        **LIBERADO,
        motivo=MENSAJE_SERVICIO_NO_DISPONIBLE,
        codigo_error="INVALID_KEY",
        alerta="cuenta",
    ),
    "RATE_LIMITED": Caso(**LIBERADO, motivo=MENSAJE_PROVEEDOR_OCUPADO, codigo_error="RATE_LIMITED"),
    "error_conexion": Caso(**LIBERADO, motivo=MENSAJE_SIN_CONEXION, codigo_error="SIN_CONEXION"),
    "timeout": Caso(**RETENIDO),
    "ilegible": Caso(**RETENIDO),
}


def test_hay_un_caso_por_cada_escenario_del_simulador():
    assert set(CASOS) == set(ESCENARIOS_RECARGA)


@dataclass
class Entorno:
    cliente: object  # httpx.AsyncClient con la sesión del cliente
    admin: object  # httpx.AsyncClient con la sesión del admin
    usuario: str
    usuario_id: int
    paquete_id: int
    sesion: object
    sim: object

    def solicitud(self, **cambios) -> dict:
        return {
            "paquete_id": self.paquete_id,
            "player_id": PLAYER_ID,
            "token_idempotencia": uuid.uuid4().hex,
        } | cambios


@pytest.fixture
async def entorno(api, sesion_bd, simulador):
    """Cliente sin saldo, admin y un paquete activo que el simulador conoce (costo 0.50, venta 0.75)."""
    # Las alertas son globales: se dan por atendidas las activas para ver solo las de este caso.
    await sesion_bd.execute(
        update(Alerta).where(Alerta.atendida_en.is_(None)).values(atendida_en=func.now())
    )
    cliente = await crear_usuario_con_clave(sesion_bd)
    admin = await crear_usuario_con_clave(sesion_bd, rol="admin")
    paquete = await crear_paquete(sesion_bd, precio_costo=COSTO, precio_venta=VENTA)
    await sesion_bd.commit()
    simulador.productos[0]["paquete_id"] = paquete.paquete_id
    simulador.productos[0]["precio"] = D(COSTO)
    simulador.retry_after = 0

    http_admin, http_cliente = api(), api()
    await iniciar_sesion(http_admin, admin.usuario)
    await iniciar_sesion(http_cliente, cliente.usuario)
    return Entorno(
        http_cliente,
        http_admin,
        cliente.usuario,
        cliente.id,
        paquete.paquete_id,
        sesion_bd,
        simulador,
    )


async def abonar(entorno: Entorno, monto: str = ABONO) -> None:
    respuesta = await entorno.admin.post(
        f"/admin/saldos/{entorno.usuario_id}/abono", json={"monto": monto, "nota": "Pago de prueba"}
    )
    assert respuesta.status_code == 201, respuesta.text


async def recargar(entorno: Entorno, escenario: str, **cambios) -> dict:
    entorno.sim.escenario_recarga = escenario
    respuesta = await entorno.cliente.post("/recargas", json=entorno.solicitud(**cambios))
    assert respuesta.status_code == 201, respuesta.text
    return respuesta.json()


async def contabilidad(entorno: Entorno) -> tuple[Decimal, Decimal]:
    """Saldos de la BD, tras comprobar que cuadran con los movimientos (CA-04)."""
    sesion = entorno.sesion
    saldo = await sesion.scalar(
        select(Saldo)
        .where(Saldo.usuario_id == entorno.usuario_id)
        .execution_options(populate_existing=True)
    )
    sumas = (
        await sesion.execute(
            select(
                suma_por_tipo("abono", "ajuste", "liberacion"),
                suma_por_tipo("reserva"),
                suma_por_tipo("liberacion"),
                suma_por_tipo("cargo"),
            ).where(Movimiento.usuario_id == entorno.usuario_id)
        )
    ).one()
    ingresos, reservas, liberaciones, cargos = sumas
    assert saldo.saldo_disponible == ingresos - reservas
    assert saldo.saldo_reservado == reservas - liberaciones - cargos
    return saldo.saldo_disponible, saldo.saldo_reservado


async def movimientos_del_pedido(entorno: Entorno, codigo: str) -> list[str]:
    from app.services.codigos import id_desde_codigo

    return list(
        await entorno.sesion.scalars(
            select(Movimiento.tipo)
            .where(Movimiento.pedido_id == id_desde_codigo(codigo))
            .order_by(Movimiento.id)
        )
    )


async def alertas_activas(entorno: Entorno) -> set[str]:
    respuesta = await entorno.admin.get("/admin/alertas")
    assert respuesta.status_code == 200
    return {a["tipo"] for a in respuesta.json()}


@pytest.mark.parametrize("escenario", list(CASOS))
async def test_recorrido_completo_por_escenario(entorno, escenario):
    caso = CASOS[escenario]
    await abonar(entorno)

    # --- El cliente recarga (fases A, B y C) ---
    solicitud = entorno.solicitud()
    entorno.sim.escenario_recarga = escenario
    creado = await entorno.cliente.post("/recargas", json=solicitud)
    assert creado.status_code == 201, creado.text
    pedido = creado.json()
    codigo = pedido["codigo"]
    assert (pedido["estado"], pedido["estado_etiqueta"]) == (caso.estado, caso.etiqueta)
    assert pedido["motivo"] == caso.motivo
    assert (pedido["monto"], pedido["moneda"]) == (VENTA, "USD")
    assert pedido["nickname"] == "Jugador7448"  # RF-26: viene de validar.php
    assert (pedido["referencia"] is not None) is (caso.estado == "EXITOSO")

    # --- Proveedor: cobró o no; nunca más de una vez (RN-04, RN-05) ---
    assert len(entorno.sim.recargas) == (1 if caso.cobra_el_proveedor else 0)
    if caso.estado == "EXITOSO":
        assert pedido["referencia"] == entorno.sim.recargas[0]["referencia"]

    # --- Contabilidad (RF-24, RN-01, RN-02, CA-04) ---
    assert await contabilidad(entorno) == (D(caso.disponible), D(caso.reservado))
    assert await movimientos_del_pedido(entorno, codigo) == list(caso.movimientos)

    # --- Lo que ve el cliente: API ---
    cliente = entorno.cliente
    detalle = (await cliente.get(f"/me/pedidos/{codigo}")).json()
    assert detalle == pedido
    historial = (await cliente.get("/me/pedidos")).json()
    assert [p["codigo"] for p in historial["pedidos"]] == [codigo]  # CA-05: incluye los fallidos
    resumen = (await cliente.get("/me/resumen")).json()
    assert (resumen["saldo_disponible"], resumen["saldo_reservado"]) == (
        caso.disponible,
        caso.reservado,
    )
    exitoso = caso.estado == "EXITOSO"
    assert resumen["recargas"] == (1 if exitoso else 0)
    assert resumen["gasto_total"] == (VENTA if exitoso else "0.00")
    fondos = (await cliente.get("/me/fondos")).json()
    assert [m["tipo"] for m in fondos["movimientos"]] == ["abono"]  # RF-34
    # CA-03: ninguna respuesta del cliente menciona el costo.
    for texto in (creado.text, str(detalle), str(historial), str(resumen), str(fondos)):
        assert "costo" not in texto.lower()

    # --- Lo que ve el cliente: páginas ---
    for ruta in (f"/historial/{codigo}", "/historial", "/inicio"):
        pagina = await cliente.get(ruta)
        assert pagina.status_code == 200, ruta
        assert caso.etiqueta in pagina.text and codigo in pagina.text, ruta
        assert "costo" not in pagina.text.lower(), ruta
    if caso.motivo:
        assert caso.motivo in (await cliente.get(f"/historial/{codigo}")).text

    # --- Idempotencia (CA-02) y RN-04: reenviar no recarga ni cambia nada ---
    reenvio = await cliente.post("/recargas", json=solicitud)
    assert reenvio.status_code == 200 and reenvio.json()["codigo"] == codigo
    assert len(entorno.sim.recargas) == (1 if caso.cobra_el_proveedor else 0)
    assert await contabilidad(entorno) == (D(caso.disponible), D(caso.reservado))

    # --- Lo que ve el admin: detalle con costo, ganancia e historial de estados ---
    admin = entorno.admin
    vista = (await admin.get(f"/admin/pedidos/{codigo}")).json()
    assert (vista["estado"], vista["error"], vista["error_code"]) == (
        caso.estado,
        caso.motivo,
        caso.codigo_error,
    )
    assert (vista["precio_venta"], vista["precio_costo"]) == (VENTA, COSTO)
    assert vista["ganancia"] == (GANANCIA if exitoso else None)  # RF-54
    ultimo = vista["eventos"][-1]
    assert (ultimo["estado_anterior"], ultimo["estado_nuevo"]) == ("PROCESANDO", caso.estado)

    listado = (await admin.get("/admin/pedidos", params={"usuario": entorno.usuario})).json()
    assert [p["codigo"] for p in listado["pedidos"]] == [codigo]
    assert listado["totales"]["exitosos"] == (1 if exitoso else 0)
    assert listado["totales"]["ganancia"] == (GANANCIA if exitoso else "0.00")
    pendientes = (
        await admin.get(
            "/admin/pedidos", params={"usuario": entorno.usuario, "solo_pendientes": True}
        )
    ).json()
    assert pendientes["total"] == (1 if caso.estado == "PENDIENTE_VERIFICAR" else 0)

    # --- Alertas y panel del admin (RN-08, RN-11) ---
    assert await alertas_activas(entorno) == ({caso.alerta} if caso.alerta else set())
    panel = await admin.get("/admin/panel")
    assert panel.status_code == 200
    assert {a["tipo"] for a in panel.json()["alertas"]} == ({caso.alerta} if caso.alerta else set())


@pytest.mark.parametrize("escenario", ["timeout", "ilegible"])
@pytest.mark.parametrize("resultado", ["exitoso", "fallido"])
async def test_el_admin_resuelve_el_pedido_en_revision(entorno, escenario, resultado):
    await abonar(entorno)
    pedido = await recargar(entorno, escenario)
    codigo = pedido["codigo"]
    assert pedido["estado"] == "PENDIENTE_VERIFICAR"
    assert await contabilidad(entorno) == (D("9.25"), D("0.75"))

    datos = {"resultado": resultado, "nota": "Verificado en el panel de VentasFF"}
    if resultado == "exitoso":
        datos["referencia"] = "EV-MANUAL01"
    resuelto = await entorno.admin.post(f"/admin/pedidos/{codigo}/resolver", json=datos)
    assert resuelto.status_code == 200, resuelto.text
    vista = resuelto.json()

    if resultado == "exitoso":
        assert (vista["estado"], vista["referencia"], vista["ganancia"]) == (
            "EXITOSO",
            "EV-MANUAL01",
            GANANCIA,
        )
        assert await contabilidad(entorno) == (D("9.25"), D("0.00"))
        assert await movimientos_del_pedido(entorno, codigo) == ["reserva", "cargo"]
    else:
        assert (vista["estado"], vista["ganancia"]) == ("FALLIDO", None)
        assert await contabilidad(entorno) == (D("10.00"), D("0.00"))
        assert await movimientos_del_pedido(entorno, codigo) == ["reserva", "liberacion"]
    ultimo = vista["eventos"][-1]
    assert ultimo["estado_anterior"] == "PENDIENTE_VERIFICAR"
    assert ultimo["creado_por"] is not None  # lo hizo un admin (RF-52)

    # El cliente ve el resultado y la resolución no llamó otra vez al proveedor (RN-04).
    visto = (await entorno.cliente.get(f"/me/pedidos/{codigo}")).json()
    assert visto["estado"] == vista["estado"]
    assert len(entorno.sim.recargas) == 1

    # Un pedido ya resuelto no se puede resolver de nuevo.
    otra = await entorno.admin.post(f"/admin/pedidos/{codigo}/resolver", json=datos)
    assert otra.status_code == 409
    assert await contabilidad(entorno) == (
        (D("9.25"), D("0.00")) if resultado == "exitoso" else (D("10.00"), D("0.00"))
    )


async def test_secuencia_mixta_de_escenarios_mantiene_las_cuentas(entorno):
    """Varias recargas seguidas con resultados distintos: cada una deja su rastro y CA-04 se cumple."""
    await abonar(entorno)
    secuencia = [
        ("ok", "EXITOSO", ("9.25", "0.00")),
        ("PURCHASE_FAILED", "FALLIDO", ("9.25", "0.00")),
        ("timeout", "PENDIENTE_VERIFICAR", ("8.50", "0.75")),
        ("INSUFFICIENT_CREDIT", "FALLIDO", ("8.50", "0.75")),
        ("nickname_null", "EXITOSO", ("7.75", "0.75")),
    ]
    codigos = []
    for escenario, estado, (disponible, reservado) in secuencia:
        pedido = await recargar(entorno, escenario)
        assert pedido["estado"] == estado, escenario
        assert await contabilidad(entorno) == (D(disponible), D(reservado)), escenario
        codigos.append(pedido["codigo"])
    assert len(set(codigos)) == len(codigos)  # códigos únicos (RF-30)
    assert len(entorno.sim.recargas) == 3  # ok, timeout y nickname_null cobraron

    resumen = (await entorno.cliente.get("/me/resumen")).json()
    assert (resumen["recargas"], resumen["gasto_total"]) == (2, "1.50")
    historial = (await entorno.cliente.get("/me/pedidos")).json()
    assert [p["codigo"] for p in historial["pedidos"]] == codigos[::-1]  # del más reciente

    # El admin resuelve el pendiente como exitoso y todo cuadra: 3 cobradas, nada retenido.
    resuelto = await entorno.admin.post(
        f"/admin/pedidos/{codigos[2]}/resolver",
        json={"resultado": "exitoso", "nota": "Confirmado con el proveedor"},
    )
    assert resuelto.status_code == 200
    assert await contabilidad(entorno) == (D("7.75"), D("0.00"))


async def test_saldo_insuficiente_no_crea_pedido_ni_llama_al_proveedor(entorno):
    await abonar(entorno, "0.50")  # menos que el precio de 0.75
    respuesta = await entorno.cliente.post("/recargas", json=entorno.solicitud())
    assert respuesta.status_code == 422 and "Saldo insuficiente" in respuesta.json()["detail"]
    assert entorno.sim.recargas == []
    assert (await entorno.cliente.get("/me/pedidos")).json()["total"] == 0
    assert await contabilidad(entorno) == (D("0.50"), D("0.00"))
