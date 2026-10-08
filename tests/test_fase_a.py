"""T-044: Fase A, reserva y creación del pedido con idempotencia (RF-22, RF-25, RN-02, CA-02)."""

import asyncio
import uuid
from decimal import Decimal

import pytest
from sqlalchemy import func, select

from app.db import crear_fabrica_sesiones
from app.models import Movimiento, Pedido, PedidoEvento, Saldo
from app.services import catalogo, ledger
from app.services.ledger import SaldoInsuficiente
from app.services.recarga_service import (
    ConfirmacionRequerida,
    JugadorNoExiste,
    PaqueteNoDisponible,
    TokenInvalido,
    crear_pedido,
)
from app.services.ventasff_client import ClienteVentasFF
from tests.fake_ventasff import SimuladorVentasFF
from tests.utilidades import crear_paquete

D = Decimal
BASE = "http://simulador/api/reseller"


@pytest.fixture
async def escenario(sesion_bd, cuenta, admin_id):
    """Cliente con 10.00 y un paquete activo de venta 0.75 (costo 0.50)."""
    await ledger.abonar(sesion_bd, cuenta, D("10.00"), nota="abono", creado_por=admin_id)
    paquete = await crear_paquete(sesion_bd)
    await sesion_bd.commit()
    return cuenta, paquete.paquete_id


async def crear(sesion, sim, usuario_id, paquete_id, token=None, **kwargs):
    async with ClienteVentasFF(sim.api_key, BASE, transport=sim.transporte()) as cliente:
        return await crear_pedido(
            sesion, cliente, usuario_id, paquete_id, "75807448", token or uuid.uuid4().hex, **kwargs
        )


async def saldo(sesion, usuario_id):
    fila = await sesion.scalar(
        select(Saldo)
        .where(Saldo.usuario_id == usuario_id)
        .execution_options(populate_existing=True)
    )
    return fila.saldo_disponible, fila.saldo_reservado


async def contar(sesion, modelo, *condiciones):
    return await sesion.scalar(select(func.count()).select_from(modelo).where(*condiciones))


async def test_crea_pedido_procesando_con_reserva(sesion_bd, escenario):
    usuario_id, paquete_id = escenario
    sim = SimuladorVentasFF()
    creado = await crear(sesion_bd, sim, usuario_id, paquete_id)
    pedido = creado.pedido

    assert creado.nuevo
    assert pedido.estado == "PROCESANDO"
    assert pedido.codigo == f"FF-{pedido.id:06d}"
    assert pedido.nickname == "Jugador7448"
    assert (pedido.precio_costo, pedido.precio_venta) == (D("0.50"), D("0.75"))
    assert await saldo(sesion_bd, usuario_id) == (D("9.25"), D("0.75"))
    reserva = await sesion_bd.scalar(select(Movimiento).where(Movimiento.pedido_id == pedido.id))
    assert (reserva.tipo, reserva.monto) == ("reserva", D("0.75"))
    eventos = await sesion_bd.execute(
        select(PedidoEvento.estado_anterior, PedidoEvento.estado_nuevo)
        .where(PedidoEvento.pedido_id == pedido.id)
        .order_by(PedidoEvento.id)
    )
    assert eventos.all() == [(None, "CREADO"), ("CREADO", "PROCESANDO")]
    # Fase A no llama a recargar.php.
    assert not any(ruta.endswith("recargar.php") for _, ruta in sim.peticiones)


async def test_reenvio_con_mismo_token_devuelve_el_mismo_pedido(sesion_bd, escenario):
    usuario_id, paquete_id = escenario
    sim = SimuladorVentasFF()
    primero = await crear(sesion_bd, sim, usuario_id, paquete_id, token="tok-reenvio")
    segundo = await crear(sesion_bd, sim, usuario_id, paquete_id, token="tok-reenvio")

    assert (primero.nuevo, segundo.nuevo) == (True, False)
    assert segundo.pedido.id == primero.pedido.id
    assert await contar(sesion_bd, Movimiento, Movimiento.pedido_id == primero.pedido.id) == 1
    assert await saldo(sesion_bd, usuario_id) == (D("9.25"), D("0.75"))
    # El reenvío no vuelve a validar.
    assert sim.peticiones.count(("GET", "/api/reseller/validar.php")) == 1


async def test_doble_envio_simultaneo_crea_un_solo_pedido(sesion_bd, motor_bd, escenario):
    """CA-02: dos envíos concurrentes con el mismo token."""
    usuario_id, paquete_id = escenario
    fabrica = crear_fabrica_sesiones(motor_bd)
    sim = SimuladorVentasFF()

    async def enviar():
        async with fabrica() as sesion:
            return await crear(sesion, sim, usuario_id, paquete_id, token="tok-doble")

    resultados = await asyncio.gather(enviar(), enviar())

    assert sorted(r.nuevo for r in resultados) == [False, True]
    assert resultados[0].pedido.id == resultados[1].pedido.id
    assert await contar(sesion_bd, Pedido, Pedido.token_idempotencia == "tok-doble") == 1
    assert await saldo(sesion_bd, usuario_id) == (D("9.25"), D("0.75"))


async def test_saldo_insuficiente_no_crea_pedido(sesion_bd, escenario):
    usuario_id, _ = escenario
    caro = await crear_paquete(sesion_bd, precio_costo="9.00", precio_venta="10.01")
    await sesion_bd.commit()
    with pytest.raises(SaldoInsuficiente):
        await crear(sesion_bd, SimuladorVentasFF(), usuario_id, caro.paquete_id, token="tok-sin")
    assert await contar(sesion_bd, Pedido, Pedido.token_idempotencia == "tok-sin") == 0
    assert await saldo(sesion_bd, usuario_id) == (D("10.00"), D("0.00"))


async def test_jugador_inexistente_no_crea_pedido(sesion_bd, escenario):
    usuario_id, paquete_id = escenario
    sim = SimuladorVentasFF(escenario_validar="no_existe")
    with pytest.raises(JugadorNoExiste):
        await crear(sesion_bd, sim, usuario_id, paquete_id, token="tok-noexiste")
    assert await contar(sesion_bd, Pedido, Pedido.token_idempotencia == "tok-noexiste") == 0


async def test_no_disponible_exige_confirmacion(sesion_bd, escenario):
    usuario_id, paquete_id = escenario
    sim = SimuladorVentasFF(escenario_validar="no_disponible")
    with pytest.raises(ConfirmacionRequerida) as error:
        await crear(sesion_bd, sim, usuario_id, paquete_id, token="tok-conf")
    assert error.value.advertencia

    creado = await crear(
        sesion_bd, sim, usuario_id, paquete_id, token="tok-conf", confirmar_sin_verificar=True
    )
    assert creado.nuevo
    assert creado.pedido.nickname is None


async def test_precio_congelado(sesion_bd, escenario):
    """RN-02: un cambio de precio posterior no altera el pedido."""
    usuario_id, paquete_id = escenario
    creado = await crear(sesion_bd, SimuladorVentasFF(), usuario_id, paquete_id)
    await catalogo.fijar_precio_venta(sesion_bd, paquete_id, D("1.50"))
    await sesion_bd.commit()
    pedido = await sesion_bd.scalar(
        select(Pedido)
        .where(Pedido.id == creado.pedido.id)
        .execution_options(populate_existing=True)
    )
    assert pedido.precio_venta == D("0.75")


async def test_paquete_inactivo(sesion_bd, escenario):
    usuario_id, _ = escenario
    inactivo = await crear_paquete(sesion_bd, activo=False)
    await sesion_bd.commit()
    with pytest.raises(PaqueteNoDisponible):
        await crear(sesion_bd, SimuladorVentasFF(), usuario_id, inactivo.paquete_id)


@pytest.mark.parametrize("token", ["", "   ", "x" * 201, None])
async def test_token_invalido(sesion_bd, escenario, token):
    usuario_id, paquete_id = escenario
    async with ClienteVentasFF("rv_c_simulador", BASE) as cliente:
        with pytest.raises(TokenInvalido):
            await crear_pedido(sesion_bd, cliente, usuario_id, paquete_id, "75807448", token)
