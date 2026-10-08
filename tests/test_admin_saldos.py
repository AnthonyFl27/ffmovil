"""T-056: abonos y ajustes del admin con nota obligatoria (RF-40, RF-41, RF-42, RF-55)."""

from sqlalchemy import select

from app.models import Auditoria, Movimiento
from tests.utilidades_api import crear_usuario_con_clave, iniciar_sesion


async def preparar(api, sesion_bd):
    admin = await crear_usuario_con_clave(sesion_bd, rol="admin")
    cliente = await crear_usuario_con_clave(sesion_bd)
    c = api()
    await iniciar_sesion(c, admin.usuario)
    return c, admin.id, cliente.id


async def test_abono_y_ajustes(api, sesion_bd):
    c, admin_id, cliente_id = await preparar(api, sesion_bd)
    abono = await c.post(
        f"/admin/saldos/{cliente_id}/abono", json={"monto": "20.00", "nota": "Yape ref 99"}
    )
    assert abono.status_code == 201
    assert (abono.json()["tipo"], abono.json()["monto"]) == ("abono", "20.00")
    assert abono.json()["saldo_disponible_resultante"] == "20.00"

    negativo = await c.post(
        f"/admin/saldos/{cliente_id}/ajuste", json={"monto": "-2.50", "nota": "Corrección"}
    )
    positivo = await c.post(
        f"/admin/saldos/{cliente_id}/ajuste", json={"monto": "1", "nota": "Bonificación"}
    )
    assert negativo.status_code == positivo.status_code == 201
    assert positivo.json()["saldo_disponible_resultante"] == "18.50"

    # RF-42: cada cambio queda en el libro; RF-55: y en la auditoría.
    movimientos = (
        await sesion_bd.scalars(
            select(Movimiento.tipo)
            .where(Movimiento.usuario_id == cliente_id)
            .order_by(Movimiento.id)
        )
    ).all()
    assert movimientos == ["abono", "ajuste", "ajuste"]
    auditoria = (
        await sesion_bd.execute(
            select(Auditoria.accion, Auditoria.detalle)
            .where(Auditoria.usuario_id == admin_id)
            .order_by(Auditoria.id)
        )
    ).all()
    assert [a for a, _ in auditoria] == ["abono", "ajuste", "ajuste"]
    assert auditoria[1][1] | {"movimiento_id": None} == {
        "usuario_id": cliente_id,
        "movimiento_id": None,
        "monto": "-2.50",
        "nota": "Corrección",
    }

    # El cliente ve el abono y los ajustes en Fondos (RF-34).
    sesion_cliente = api()
    usuario = (await c.get("/admin/usuarios")).json()
    nombre = next(u["usuario"] for u in usuario if u["id"] == cliente_id)
    await iniciar_sesion(sesion_cliente, nombre)
    fondos = (await sesion_cliente.get("/me/fondos")).json()
    assert fondos["saldo_disponible"] == "18.50"
    assert len(fondos["movimientos"]) == 3


async def test_rechazos_sin_movimiento(api, sesion_bd):
    c, admin_id, cliente_id = await preparar(api, sesion_bd)
    casos = [
        ("abono", {"monto": "5", "nota": "  "}, 422),
        ("abono", {"monto": "5"}, 422),
        ("abono", {"monto": "0", "nota": "x"}, 422),
        ("abono", {"monto": "-5", "nota": "x"}, 422),
        ("abono", {"monto": "1.001", "nota": "x"}, 422),
        ("ajuste", {"monto": "0", "nota": "x"}, 422),
        # RN-01: un ajuste no deja el saldo en negativo.
        ("ajuste", {"monto": "-1", "nota": "x"}, 422),
    ]
    for tipo, cuerpo, esperado in casos:
        respuesta = await c.post(f"/admin/saldos/{cliente_id}/{tipo}", json=cuerpo)
        assert respuesta.status_code == esperado, (tipo, cuerpo, respuesta.text)
    # Un admin no tiene cuenta de saldo; un id inexistente tampoco.
    for usuario_id in (admin_id, 999999999):
        respuesta = await c.post(
            f"/admin/saldos/{usuario_id}/abono", json={"monto": "1", "nota": "x"}
        )
        assert respuesta.status_code == 404
    hay = await sesion_bd.scalar(select(Movimiento.id).where(Movimiento.usuario_id == cliente_id))
    assert hay is None
    assert (
        await sesion_bd.scalar(select(Auditoria.id).where(Auditoria.usuario_id == admin_id)) is None
    )
