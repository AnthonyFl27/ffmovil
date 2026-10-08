"""Esquemas de respuesta para el cliente (no administrador).

Regla (RF-35, CA-03): los esquemas de este módulo y de cualquier `app/schemas/*.py`
que no empiece por `admin` no declaran campos de costo (`precio_costo` u otros con
"costo" en el nombre o en el alias). Así el cliente nunca recibe el precio de costo,
ni en la API ni en el HTML. Los esquemas de administración irán en
`app/schemas/admin*.py`.
"""

from decimal import Decimal

from pydantic import BaseModel, ConfigDict


class PaqueteCliente(BaseModel):
    """Paquete activo tal como se muestra al cliente (RF-13)."""

    model_config = ConfigDict(from_attributes=True)

    paquete_id: int
    nombre: str
    diamantes: int | None
    precio_venta: Decimal
