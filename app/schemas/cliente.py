"""Esquemas de respuesta para el cliente (no administrador).

Regla (RF-35, CA-03): los esquemas de este módulo y de cualquier `app/schemas/*.py`
que no empiece por `admin` no declaran campos de costo (`precio_costo` u otros con
"costo" en el nombre o en el alias). Así el cliente nunca recibe el precio de costo,
ni en la API ni en el HTML. Los esquemas de administración irán en
`app/schemas/admin*.py`.
"""

from datetime import datetime
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, PlainSerializer

# RF-36: montos en USD, como texto con 2 decimales (nunca float, RNF-04).
Monto = Annotated[Decimal, PlainSerializer(lambda v: f"{v:.2f}", return_type=str)]
MONEDA = "USD"


class PaqueteCliente(BaseModel):
    """Paquete activo tal como se muestra al cliente (RF-13)."""

    model_config = ConfigDict(from_attributes=True)

    paquete_id: int
    nombre: str
    diamantes: int | None
    precio_venta: Monto


class Resumen(BaseModel):
    """Inicio del cliente (RF-33): gasto y recargas cuentan solo pedidos EXITOSO."""

    saldo_disponible: Monto
    saldo_reservado: Monto
    gasto_total: Monto
    recargas: int
    moneda: Literal["USD"] = MONEDA


class MovimientoFondos(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    fecha: datetime
    tipo: Literal["abono", "ajuste"]
    monto: Monto
    nota: str | None


class Fondos(BaseModel):
    """Pantalla Fondos (RF-34): saldo y abonos y ajustes, los más recientes primero."""

    saldo_disponible: Monto
    saldo_reservado: Monto
    moneda: Literal["USD"] = MONEDA
    movimientos: list[MovimientoFondos]
