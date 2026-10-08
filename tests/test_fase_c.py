"""T-046: resolución por escenario del simulador, con su contabilidad (RF-24, RN-02, RN-04)."""

import uuid
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.db import crear_fabrica_sesiones
from app.models import Movimiento, Pedido, PedidoEvento, Saldo
from app.services import ledger
from app.services.estados import TransicionInvalida
from app.services.limitador import LimitadorTasa
from app.services.recarga_service import (
    MENSAJE_PROVEEDOR_OCUPADO,
    MENSAJE_SERVICIO_NO_DISPONIBLE,
    MENSAJE_SIN_CONEXION,
    MENSAJE_SIN_DISPONIBILIDAD,
    ResultadoProveedor,
    crear_pedido,
    procesar_pedido,
    resolver_pedido,
)
from app.services.ventasff_client import Clasificacion, ClienteVentasFF
from tests.fake_ventasff import SimuladorVentasFF
from tests.utilidades import crear_paquete

D = Decimal
BASE = "http://simulador/api/reseller"


async def sin_espera(_segundos):
    return None


@pytest.fixture
async def escenario(sesion_bd, cuenta, admin_id):
    """Cliente con 10.00 y paquete activo (costo 0.81, venta 0.91) con id 1 del simulador."""
    await ledger.abonar(sesion_bd, cuenta, D("10.00"), nota="abono", creado_por=admin_id)
    paquete = await crear_paquete(sesion_bd)
    await sesion_bd.commit()
    return cuenta, paquete


async def recargar(sesion, motor, sim, usuario_id, paquete):
    # El simulador conoce el paquete 1; el pedido usa el id local del paquete de prueba.
    sim.productos[0]["paquete_id"] = paquete.paquete_id
    async with ClienteVentasFF(sim.api_key, BASE, transport=sim.transporte()) as cliente:
        creado = await crear_pedido(
            sesion, cliente, usuario_id, paquete.paquete_id, "75807448", uuid.uuid4().hex
        )
        return await procesar_pedido(
            crear_fabrica_sesiones(motor),
            motor,
            cliente,
            LimitadorTasa(8),
            creado.pedido.id,
            dormir=sin_espera,
        )


async def estado_contable(sesion, usuario_id, pedido_id):
    saldo = await sesion.scalar(
        select(Saldo)
        .where(Saldo.usuario_id == usuario_id)
        .execution_options(populate_existing=True)
    )
    tipos = list(
        await sesion.scalars(
            select(Movimiento.tipo).where(Movimiento.pedido_id == pedido_id).order_by(Movimiento.id)
        )
    )
    return (saldo.saldo_disponible, saldo.saldo_reservado), tipos


EXITO = ("EXITOSO", (D("9.09"), D("0.00")), ["reserva", "cargo"])
RETENIDO = ("PENDIENTE_VERIFICAR", (D("9.09"), D("0.91")), ["reserva"])
LIBERADO = ("FALLIDO", (D("10.00"), D("0.00")), ["reserva", "liberacion"])

CASOS = {
    # escenario: (estado, saldo (disp, reservado), movimientos, motivo, error_code, ¿cobró el proveedor?)
    "ok": (*EXITO, None, None, True),
    "nickname_null": (*EXITO, None, None, True),
    "PURCHASE_FAILED": (*LIBERADO, "Paquete no disponible", "PURCHASE_FAILED", False),
    "BUSY": (*LIBERADO, MENSAJE_PROVEEDOR_OCUPADO, "BUSY", False),
    "INSUFFICIENT_CREDIT": (*LIBERADO, MENSAJE_SIN_DISPONIBILIDAD, "INSUFFICIENT_CREDIT", False),
    "INVALID_KEY": (*LIBERADO, MENSAJE_SERVICIO_NO_DISPONIBLE, "INVALID_KEY", False),
    "RATE_LIMITED": (*LIBERADO, MENSAJE_PROVEEDOR_OCUPADO, "RATE_LIMITED", False),
    "error_conexion": (*LIBERADO, MENSAJE_SIN_CONEXION, "SIN_CONEXION", False),
    "timeout": (*RETENIDO, None, None, True),
    "ilegible": (*RETENIDO, None, None, True),
}


@pytest.mark.parametrize("escenario_sim", list(CASOS))
async def test_resolucion_por_escenario(sesion_bd, motor_bd, escenario, escenario_sim):
    usuario_id, paquete = escenario
    estado, saldo, movimientos, motivo, codigo, cobrado = CASOS[escenario_sim]
    sim = SimuladorVentasFF(escenario_recarga=escenario_sim)

    pedido, _ = await recargar(sesion_bd, motor_bd, sim, usuario_id, paquete)

    assert pedido.estado == estado
    assert (pedido.error, pedido.error_code) == (motivo, codigo)
    assert await estado_contable(sesion_bd, usuario_id, pedido.id) == (saldo, movimientos)
    assert bool(sim.recargas) is cobrado
    if estado == "EXITOSO":
        assert pedido.referencia == sim.recargas[0]["referencia"]
        # RF-26: el nickname viene de validar.php aunque recargar.php devuelva null.
        assert pedido.nickname == "Jugador7448"
    else:
        assert pedido.referencia is None
    ultimo = await sesion_bd.scalar(
        select(PedidoEvento)
        .where(PedidoEvento.pedido_id == pedido.id)
        .order_by(PedidoEvento.id.desc())
        .limit(1)
    )
    assert (ultimo.estado_anterior, ultimo.estado_nuevo) == ("PROCESANDO", estado)


async def test_sin_credito_del_proveedor_falla_sin_recargar(sesion_bd, motor_bd, escenario):
    usuario_id, paquete = escenario
    sim = SimuladorVentasFF(credito=D("0.50"))
    pedido, resultado = await recargar(sesion_bd, motor_bd, sim, usuario_id, paquete)
    assert (pedido.estado, pedido.error_code, resultado.alerta) == (
        "FALLIDO",
        "SIN_CREDITO_PROVEEDOR",
        "credito",
    )
    assert await estado_contable(sesion_bd, usuario_id, pedido.id) == LIBERADO[1:]


async def test_no_resuelve_un_pedido_ya_resuelto(sesion_bd, motor_bd, escenario):
    usuario_id, paquete = escenario
    pedido, _ = await recargar(sesion_bd, motor_bd, SimuladorVentasFF(), usuario_id, paquete)
    with pytest.raises(TransicionInvalida):
        await resolver_pedido(
            sesion_bd, pedido.id, ResultadoProveedor(Clasificacion.ERROR_API, motivo="x")
        )
    assert await estado_contable(sesion_bd, usuario_id, pedido.id) == EXITO[1:]


async def test_pendiente_no_se_procesa_de_nuevo(sesion_bd, motor_bd, escenario):
    """RN-04: un PENDIENTE_VERIFICAR nunca se reintenta automáticamente."""
    usuario_id, paquete = escenario
    sim = SimuladorVentasFF(escenario_recarga="timeout")
    pedido, _ = await recargar(sesion_bd, motor_bd, sim, usuario_id, paquete)
    async with ClienteVentasFF(sim.api_key, BASE, transport=sim.transporte()) as cliente:
        with pytest.raises(TransicionInvalida):
            await procesar_pedido(
                crear_fabrica_sesiones(motor_bd),
                motor_bd,
                cliente,
                LimitadorTasa(8),
                pedido.id,
                dormir=sin_espera,
            )
    assert len(sim.recargas) == 1
    actual = await sesion_bd.scalar(
        select(Pedido.estado)
        .where(Pedido.id == pedido.id)
        .execution_options(populate_existing=True)
    )
    assert actual == "PENDIENTE_VERIFICAR"
