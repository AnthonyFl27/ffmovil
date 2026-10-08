"""Ayudas compartidas por las pruebas de base de datos."""

import uuid

from app.models import Usuario


def nuevo_usuario(rol: str = "cliente") -> Usuario:
    return Usuario(usuario=f"u_{uuid.uuid4().hex[:12]}", hash_password="x", rol=rol)


async def crear_usuario(sesion, rol: str = "cliente") -> Usuario:
    usuario = nuevo_usuario(rol)
    sesion.add(usuario)
    await sesion.flush()
    return usuario


async def crear_paquete(sesion, precio_costo="0.81", precio_venta="0.91", activo=True):
    """Paquete free_fire con id aleatorio (el esquema `test` es compartido)."""
    import random
    from decimal import Decimal

    from app.models import Paquete

    paquete = Paquete(
        paquete_id=random.randint(1_000_000_000, 2_000_000_000),
        juego="free_fire",
        nombre="110 Diamantes",
        diamantes=110,
        precio_costo=Decimal(precio_costo),
        precio_venta=Decimal(precio_venta) if precio_venta is not None else None,
        activo=activo,
    )
    sesion.add(paquete)
    await sesion.flush()
    return paquete


async def crear_pedido(sesion, usuario_id, paquete, **cambios):
    from app.models import Pedido

    datos = {
        "usuario_id": usuario_id,
        "paquete_id": paquete.paquete_id,
        "player_id": "75807448",
        "precio_costo": paquete.precio_costo,
        "precio_venta": paquete.precio_venta,
        "estado": "PROCESANDO",
        "token_idempotencia": uuid.uuid4().hex,
    } | cambios
    pedido = Pedido(**datos)
    sesion.add(pedido)
    await sesion.flush()
    return pedido
