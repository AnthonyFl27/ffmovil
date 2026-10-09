"""T-077: ninguna plantilla ni página del cliente muestra `precio_costo` (RF-35, CA-03)."""

import re
from decimal import Decimal
from pathlib import Path

from app.web.plantillas import DIRECTORIO_PLANTILLAS
from tests.utilidades import crear_paquete, crear_pedido
from tests.utilidades_api import crear_usuario_con_clave, iniciar_sesion
from tests.utilidades_web import htmx_get, htmx_post

# Costo con un valor que no aparece en ningún otro lado de la página.
COSTO = "0.37"
VENTA = "0.75"

# Plantillas que pueden llegar a un cliente: todo menos el panel admin.
PLANTILLAS_CLIENTE = [
    p
    for p in DIRECTORIO_PLANTILLAS.rglob("*.html")
    if "admin" not in p.relative_to(DIRECTORIO_PLANTILLAS).parts
]


def test_plantillas_del_cliente_no_mencionan_costo():
    assert any(p.parent.name == "cliente" for p in PLANTILLAS_CLIENTE)
    for plantilla in PLANTILLAS_CLIENTE:
        contenido = Path(plantilla).read_text(encoding="utf-8").lower()
        assert "costo" not in contenido, plantilla
        assert "ganancia" not in contenido, plantilla


def sin_costo(html: str) -> None:
    assert "costo" not in html.lower()
    assert "ganancia" not in html.lower()
    assert not re.search(rf"\b{re.escape(COSTO)}\b", html)


async def test_paginas_del_cliente_no_contienen_el_costo(api, sesion_bd, simulador):
    usuario = await crear_usuario_con_clave(sesion_bd)
    admin = await crear_usuario_con_clave(sesion_bd, rol="admin")
    paquete = await crear_paquete(sesion_bd, precio_costo=COSTO, precio_venta=VENTA)
    from app.services import ledger
    from app.services.codigos import codigo_pedido

    await ledger.abonar(sesion_bd, usuario.id, Decimal("5.00"), nota="Abono", creado_por=admin.id)
    pedido = await crear_pedido(sesion_bd, usuario.id, paquete, estado="EXITOSO")
    pedido.codigo = codigo_pedido(pedido.id)
    await sesion_bd.commit()
    simulador.productos[0]["paquete_id"] = paquete.paquete_id
    simulador.productos[0]["precio"] = Decimal(COSTO)

    http = api()
    await iniciar_sesion(http, usuario.usuario)
    respuestas = [
        await http.get("/login", follow_redirects=True),
        await http.get("/inicio"),
        await http.get("/recargar"),
        await http.get("/historial"),
        await htmx_get(http, "/historial", "pedidos", estado="EXITOSO"),
        await http.get(f"/historial/{pedido.codigo}"),
        await htmx_get(http, f"/historial/{pedido.codigo}"),
        await http.get("/fondos"),
        await http.get("/clave"),
    ]

    def ocultos(html: str) -> dict:
        return dict(re.findall(r'<input type="hidden" name="(\w+)" value="([^"]*)">', html))

    # Recarga en tres pasos (CHG-010): ninguno de los fragmentos lleva el costo.
    validacion = await htmx_post(http, "/recargar/validar", {"player_id": "75807448"})
    resumen = await htmx_post(
        http,
        "/recargar/resumen",
        ocultos(validacion.text) | {"paquete_id": str(paquete.paquete_id)},
    )
    confirmacion = await htmx_post(http, "/recargar/confirmar", ocultos(resumen.text))
    respuestas += [validacion, resumen, confirmacion]

    assert "Exitoso" in confirmacion.text
    for respuesta in respuestas:
        assert respuesta.status_code == 200, respuesta.url
        sin_costo(respuesta.text)
