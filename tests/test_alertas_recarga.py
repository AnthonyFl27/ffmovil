"""T-049: alertas al admin generadas por el flujo de recarga (RN-08, RN-11)."""

from decimal import Decimal

import pytest
from sqlalchemy import func, select, update

from app.models import Alerta
from tests.fake_ventasff import SimuladorVentasFF
from tests.test_fase_c import escenario, recargar  # noqa: F401  (fixture reutilizada)


async def limpiar_alertas(sesion):
    """La tabla es compartida: se dan por atendidas las activas antes de cada caso."""
    await sesion.execute(
        update(Alerta).where(Alerta.atendida_en.is_(None)).values(atendida_en=func.now())
    )
    await sesion.commit()


async def activas(sesion) -> dict[str, str]:
    filas = await sesion.execute(
        select(Alerta.tipo, Alerta.mensaje)
        .where(Alerta.atendida_en.is_(None))
        .execution_options(populate_existing=True)
    )
    return dict(filas.all())


@pytest.mark.parametrize(
    ("simulador", "tipo", "texto"),
    [
        ({"escenario_recarga": "INSUFFICIENT_CREDIT"}, "sin_credito", "INSUFFICIENT_CREDIT"),
        ({"credito": Decimal("0.49")}, "sin_credito", "SIN_CREDITO_PROVEEDOR"),
        ({"escenario_recarga": "INVALID_KEY"}, "cuenta", "INVALID_KEY"),
        # Tras la recarga de 0.50 quedan 9.90, por debajo del umbral de 10.00.
        ({"credito": Decimal("10.40")}, "credito_bajo", "9.90"),
    ],
)
async def test_flujo_genera_alerta(sesion_bd, motor_bd, escenario, simulador, tipo, texto):  # noqa: F811
    await limpiar_alertas(sesion_bd)
    usuario_id, paquete = escenario
    await recargar(sesion_bd, motor_bd, SimuladorVentasFF(**simulador), usuario_id, paquete)
    alertas = await activas(sesion_bd)
    assert tipo in alertas
    assert texto in alertas[tipo]
    assert "rv_c_" not in alertas[tipo]


async def test_credito_suficiente_no_alerta(sesion_bd, motor_bd, escenario):  # noqa: F811
    await limpiar_alertas(sesion_bd)
    usuario_id, paquete = escenario
    pedido, _ = await recargar(sesion_bd, motor_bd, SimuladorVentasFF(), usuario_id, paquete)
    assert pedido.estado == "EXITOSO"
    assert await activas(sesion_bd) == {}


async def test_no_duplica_alerta_activa(sesion_bd, motor_bd, escenario):  # noqa: F811
    await limpiar_alertas(sesion_bd)
    usuario_id, paquete = escenario
    for _ in range(2):
        sim = SimuladorVentasFF(escenario_recarga="INVALID_KEY")
        await recargar(sesion_bd, motor_bd, sim, usuario_id, paquete)
    total = await sesion_bd.scalar(
        select(func.count())
        .select_from(Alerta)
        .where(Alerta.tipo == "cuenta", Alerta.atendida_en.is_(None))
    )
    assert total == 1
