"""Pruebas de las alertas al admin (RN-08, RN-11).

El esquema `test` es compartido por toda la sesión: cada prueba que crea alertas
cierra primero las activas dentro de su transacción y termina con rollback.
"""

from decimal import Decimal

import pytest
from sqlalchemy import func, select, update

from app.models import Alerta, Auditoria, Config
from app.services.alertas import (
    CLAVE_UMBRAL,
    UMBRAL_POR_DEFECTO,
    AlertaInexistente,
    alertas_activas,
    atender_alerta,
    comprobar_credito,
    registrar_alerta,
    umbral_credito,
)


async def _cerrar_activas(sesion) -> None:
    await sesion.execute(
        update(Alerta).where(Alerta.atendida_en.is_(None)).values(atendida_en=func.now())
    )


async def _id_activa(sesion, tipo: str) -> int:
    consulta = select(Alerta.id).where(Alerta.tipo == tipo, Alerta.atendida_en.is_(None))
    return await sesion.scalar(consulta)


async def test_umbral_credito_lee_config_y_usa_defecto_si_es_invalido(sesion_bd):
    assert await umbral_credito(sesion_bd) == Decimal("10.00")

    await sesion_bd.execute(update(Config).where(Config.clave == CLAVE_UMBRAL).values(valor="abc"))
    assert await umbral_credito(sesion_bd) == UMBRAL_POR_DEFECTO

    await sesion_bd.execute(update(Config).where(Config.clave == CLAVE_UMBRAL).values(valor="25.5"))
    assert await umbral_credito(sesion_bd) == Decimal("25.5")
    await sesion_bd.rollback()


async def test_registrar_alerta_una_sola_activa_por_tipo(sesion_bd):
    await _cerrar_activas(sesion_bd)

    assert await registrar_alerta(sesion_bd, "sin_credito", "Sin crédito") is True
    assert await registrar_alerta(sesion_bd, "sin_credito", "Otra vez") is False
    assert await registrar_alerta(sesion_bd, "cuenta", "Cuenta inactiva") is True

    with pytest.raises(ValueError):
        await registrar_alerta(sesion_bd, "inventado", "x")
    await sesion_bd.rollback()


async def test_registrar_alerta_tras_atender_crea_otra(sesion_bd, admin_id):
    await _cerrar_activas(sesion_bd)

    assert await registrar_alerta(sesion_bd, "cuenta", "Clave inválida") is True
    await atender_alerta(sesion_bd, await _id_activa(sesion_bd, "cuenta"), admin_id=admin_id)
    assert await registrar_alerta(sesion_bd, "cuenta", "Clave inválida de nuevo") is True
    await sesion_bd.rollback()


async def test_comprobar_credito_compara_con_umbral(sesion_bd):
    await _cerrar_activas(sesion_bd)

    assert await comprobar_credito(sesion_bd, Decimal("9.99")) is True
    mensaje = await sesion_bd.scalar(
        select(Alerta.mensaje).where(Alerta.tipo == "credito_bajo", Alerta.atendida_en.is_(None))
    )
    assert "9.99" in mensaje and "10.00" in mensaje

    assert await comprobar_credito(sesion_bd, Decimal("10.00")) is False
    assert await comprobar_credito(sesion_bd, Decimal(50)) is False
    await sesion_bd.rollback()


async def test_atender_alerta_marca_audita_y_es_idempotente(sesion_bd, admin_id):
    await _cerrar_activas(sesion_bd)
    await registrar_alerta(sesion_bd, "sin_credito", "Sin crédito")
    alerta_id = await _id_activa(sesion_bd, "sin_credito")

    atendida = await atender_alerta(sesion_bd, alerta_id, admin_id=admin_id, ip="127.0.0.1")
    assert atendida.atendida_en is not None
    assert atendida.atendida_por == admin_id
    primera_marca = atendida.atendida_en

    otra_vez = await atender_alerta(sesion_bd, alerta_id, admin_id=admin_id)
    assert otra_vez.atendida_en == primera_marca

    auditorias = await sesion_bd.scalar(
        select(func.count(Auditoria.id)).where(
            Auditoria.accion == "atender_alerta",
            Auditoria.detalle["alerta"].astext == str(alerta_id),
        )
    )
    assert auditorias == 1

    with pytest.raises(AlertaInexistente):
        await atender_alerta(sesion_bd, 999_999_999_999, admin_id=admin_id)
    await sesion_bd.rollback()


async def test_alertas_activas_excluye_atendidas(sesion_bd, admin_id):
    await _cerrar_activas(sesion_bd)
    await registrar_alerta(sesion_bd, "sin_credito", "Sin crédito")
    await registrar_alerta(sesion_bd, "cuenta", "Cuenta inactiva")
    atendida = await _id_activa(sesion_bd, "cuenta")
    await atender_alerta(sesion_bd, atendida, admin_id=admin_id)

    ids = [a.id for a in await alertas_activas(sesion_bd)]
    assert atendida not in ids
    assert await _id_activa(sesion_bd, "sin_credito") in ids
    await sesion_bd.rollback()
