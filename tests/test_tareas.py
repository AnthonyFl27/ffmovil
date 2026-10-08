"""T-033: sincronización programada y registro de resultado (RF-10, plan sec. 5)."""

import json
import random
from datetime import datetime
from decimal import Decimal

import pytest
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy import select

from app.db import crear_fabrica_sesiones
from app.models import Config, Paquete
from app.services import tareas
from app.services.ventasff_client import ClienteVentasFF
from tests.fake_ventasff import SimuladorVentasFF

D = Decimal
BASE = "http://simulador/api/reseller"
CLAVE_CLIENTE = "rv_c_simulador"


def producto(paquete_id, precio=None, juego="free_fire"):
    return {
        "paquete_id": paquete_id,
        "nombre": f"Paquete {paquete_id}",
        "juego": juego,
        "diamantes": 100,
        "precio": precio or D("0.50"),
        "currency": "USD",
        "dato_extra": None if juego == "free_fire" else "Zone ID",
    }


@pytest.fixture
def ids():
    """Ids propios de la prueba: el esquema `test` se comparte en toda la sesión."""
    base = random.randint(10_000_000, 900_000_000)
    return base, base + 1, base + 2


def fabrica_y_cliente(motor, sim):
    fabrica = crear_fabrica_sesiones(motor)

    def crear_cliente():
        return ClienteVentasFF(CLAVE_CLIENTE, BASE, transport=sim.transporte())

    return fabrica, crear_cliente


async def leer_config(sesion) -> dict:
    valor = await sesion.scalar(
        select(Config.valor).where(Config.clave == tareas.CLAVE_ULTIMA_SINCRONIZACION)
    )
    return json.loads(valor)


async def test_sincronizacion_correcta_registra_resultado(motor_bd, sesion_bd, ids):
    a, b, ml = ids
    sim = SimuladorVentasFF(
        productos=[producto(a), producto(b, D("2.40")), producto(ml, juego="mobile_legends")]
    )
    fabrica, crear_cliente = fabrica_y_cliente(motor_bd, sim)

    resumen = await tareas.ejecutar_sincronizacion(fabrica, crear_cliente)

    assert resumen is not None
    assert resumen.nuevos == 2
    paquetes = (
        await sesion_bd.scalars(select(Paquete).where(Paquete.paquete_id.in_([a, b, ml])))
    ).all()
    assert sorted(p.paquete_id for p in paquetes) == sorted([a, b])

    registro = await leer_config(sesion_bd)
    assert registro["resultado"] == "ok"
    assert (registro["recibidos"], registro["nuevos"]) == (2, 2)
    assert set(registro) >= {"fecha", "actualizados", "desactivados", "bajo_costo"}
    datetime.fromisoformat(registro["fecha"])


async def test_error_de_ventasff_registra_error_sin_lanzar(motor_bd, sesion_bd):
    sim = SimuladorVentasFF()
    sim.api_key = "rv_c_otra"
    fabrica, crear_cliente = fabrica_y_cliente(motor_bd, sim)

    resumen = await tareas.ejecutar_sincronizacion(fabrica, crear_cliente)

    assert resumen is None
    registro = await leer_config(sesion_bd)
    assert registro["resultado"] == "error"
    assert "INVALID_KEY" in registro["detalle"]
    assert CLAVE_CLIENTE not in registro["detalle"]
    datetime.fromisoformat(registro["fecha"])


async def test_crear_programador_configura_la_tarea_diaria(motor_bd):
    fabrica, crear_cliente = fabrica_y_cliente(motor_bd, SimuladorVentasFF())

    programador = tareas.crear_programador(fabrica, crear_cliente)
    job = programador.get_job(tareas.ID_TAREA_SINCRONIZACION)

    assert not programador.running
    assert job is not None
    assert isinstance(job.trigger, CronTrigger)
    assert "hour='8'" in str(job.trigger)
    assert "minute='0'" in str(job.trigger)
    assert job.max_instances == 1
    assert job.coalesce is True

    otro = tareas.crear_programador(fabrica, crear_cliente, hora_utc=3)
    assert "hour='3'" in str(otro.get_job(tareas.ID_TAREA_SINCRONIZACION).trigger)
