from datetime import datetime
from decimal import Decimal

from sqlalchemy import CheckConstraint, Integer, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base

JUEGO_FREE_FIRE = "free_fire"


class Paquete(Base):
    """Paquete del catálogo de VentasFF (RF-10 a RF-14).

    `precio_costo` viene del proveedor; `precio_venta` lo fija el admin y la
    sincronización nunca lo modifica.
    """

    __tablename__ = "paquetes"
    __table_args__ = (
        # RF-11: un paquete sin precio de venta no puede activarse.
        CheckConstraint("activo = false OR precio_venta IS NOT NULL", name="activo_con_precio"),
        CheckConstraint("precio_venta IS NULL OR precio_venta > 0", name="precio_venta_positivo"),
        CheckConstraint("precio_costo >= 0", name="precio_costo_no_negativo"),
    )

    # Id de VentasFF, no autogenerado.
    paquete_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=False)
    juego: Mapped[str] = mapped_column(Text)
    nombre: Mapped[str] = mapped_column(Text)
    diamantes: Mapped[int | None]
    precio_costo: Mapped[Decimal]
    precio_venta: Mapped[Decimal | None]
    activo: Mapped[bool] = mapped_column(server_default="false")
    actualizado_en: Mapped[datetime] = mapped_column(server_default=func.now())


class Config(Base):
    """Parámetros de configuración editables (p. ej. umbral de alerta de crédito)."""

    __tablename__ = "config"

    clave: Mapped[str] = mapped_column(Text, primary_key=True)
    valor: Mapped[str] = mapped_column(Text)
