"""Ayudas para las pruebas de las páginas web (HTMX)."""

import re

import httpx

HTMX = {"HX-Request": "true"}


def csrf_de(html: str) -> str:
    """Token CSRF que la página pone en `<body hx-headers=…>`."""
    encontrado = re.search(r'"X-CSRF-Token": "([^"]+)"', html)
    assert encontrado, "la página no trae el token CSRF"
    return encontrado.group(1)


async def htmx_post(cliente: httpx.AsyncClient, ruta: str, datos: dict | None = None):
    """POST de formulario como lo envía HTMX (la cabecera CSRF ya está en el cliente)."""
    return await cliente.post(ruta, data=datos or {}, headers=HTMX)


async def htmx_get(cliente: httpx.AsyncClient, ruta: str, destino: str | None = None, **params):
    cabeceras = dict(HTMX)
    if destino:
        cabeceras["HX-Target"] = destino
    return await cliente.get(ruta, params=params, headers=cabeceras)


async def cliente_web(api, sesion, simulador=None, *, abono: str | None = "10.00"):
    """Cliente con sesión (CSRF en la cabecera), saldo y un paquete activo de 0.75.

    Si se pasa `simulador`, el paquete es el que conoce VentasFF simulado (costo 0.50).
    Devuelve (http, usuario, paquete).
    """
    from decimal import Decimal

    from app.services import ledger
    from tests.utilidades import crear_paquete
    from tests.utilidades_api import crear_usuario_con_clave, iniciar_sesion

    usuario = await crear_usuario_con_clave(sesion)
    paquete = await crear_paquete(sesion, precio_costo="0.50", precio_venta="0.75")
    if abono:
        admin = await crear_usuario_con_clave(sesion, rol="admin")
        await ledger.abonar(
            sesion, usuario.id, Decimal(abono), nota="Abono de prueba", creado_por=admin.id
        )
    await sesion.commit()
    if simulador is not None:
        simulador.productos[0]["paquete_id"] = paquete.paquete_id
        simulador.productos[0]["precio"] = Decimal("0.50")
    http = api()
    await iniciar_sesion(http, usuario.usuario)
    return http, usuario, paquete
