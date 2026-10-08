"""T-075: pantalla Fondos con saldo disponible, reservado y abonos y ajustes (RF-34)."""

from decimal import Decimal

from app.services import ledger
from tests.utilidades_api import crear_usuario_con_clave
from tests.utilidades_web import cliente_web


async def test_fondos_muestra_saldos_y_movimientos(api, sesion_bd):
    http, usuario, _ = await cliente_web(api, sesion_bd)
    admin = await crear_usuario_con_clave(sesion_bd, rol="admin")
    await ledger.ajustar(
        sesion_bd, usuario.id, Decimal("-2.50"), nota="Corrección <b>", creado_por=admin.id
    )
    await ledger.reservar(sesion_bd, usuario.id, Decimal("0.75"))
    await sesion_bd.commit()

    respuesta = await http.get("/fondos")
    assert respuesta.status_code == 200
    html = respuesta.text
    assert '<strong id="saldo-disponible">6.75 USD</strong>' in html
    assert '<strong id="saldo-reservado">0.75 USD</strong>' in html
    assert "Abono de prueba" in html and "10.00 USD" in html
    assert "-2.50 USD" in html
    # Las notas se escapan; las reservas no se listan (RF-34).
    assert "Corrección &lt;b&gt;" in html
    assert html.count("<tr>") == 1 + 2
    assert 'datetime="' in html and "data-local" in html


async def test_fondos_sin_abonos(api, sesion_bd):
    http, _, _ = await cliente_web(api, sesion_bd, abono=None)
    html = (await http.get("/fondos")).text
    assert "Todavía no tienes abonos." in html
