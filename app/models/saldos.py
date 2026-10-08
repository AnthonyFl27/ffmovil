from datetime import datetime
from decimal import Decimal

from sqlalchemy import BigInteger, CheckConstraint, ForeignKey, Identity, Index, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, valores_sql

TIPOS_MOVIMIENTO = ("abono", "reserva", "liberacion", "cargo", "ajuste")


class Saldo(Base):
    __tablename__ = "saldos"
    # RN-01: el saldo nunca queda negativo.
    __table_args__ = (
        CheckConstraint("saldo_disponible >= 0", name="disponible_no_negativo"),
        CheckConstraint("saldo_reservado >= 0", name="reservado_no_negativo"),
    )

    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"), primary_key=True)
    saldo_disponible: Mapped[Decimal] = mapped_column(server_default="0")
    saldo_reservado: Mapped[Decimal] = mapped_column(server_default="0")


class Movimiento(Base):
    """Libro contable, solo inserciones (RF-42).

    `monto` es positivo salvo en `ajuste`, que lleva signo. Efecto en el saldo:
    abono y ajuste suman al disponible; reserva pasa de disponible a reservado;
    liberación, de reservado a disponible; cargo resta del reservado.
    """

    __tablename__ = "movimientos"
    __table_args__ = (
        CheckConstraint(f"tipo IN ({valores_sql(TIPOS_MOVIMIENTO)})", name="tipo"),
        CheckConstraint("tipo = 'ajuste' OR monto > 0", name="monto_positivo"),
        CheckConstraint("tipo <> 'ajuste' OR monto <> 0", name="ajuste_no_cero"),
        CheckConstraint(
            "tipo NOT IN ('abono', 'ajuste') OR coalesce(btrim(nota), '') <> ''",
            name="nota_obligatoria",
        ),
        CheckConstraint("saldo_disponible_resultante >= 0", name="disponible_no_negativo"),
        CheckConstraint("saldo_reservado_resultante >= 0", name="reservado_no_negativo"),
        Index("ix_movimientos_usuario_id_fecha", "usuario_id", "fecha"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"))
    tipo: Mapped[str] = mapped_column(Text)
    monto: Mapped[Decimal]
    saldo_disponible_resultante: Mapped[Decimal]
    saldo_reservado_resultante: Mapped[Decimal]
    # La FK hacia `pedidos` se agrega en la migración de T-040.
    pedido_id: Mapped[int | None] = mapped_column(BigInteger)
    nota: Mapped[str | None] = mapped_column(Text)
    creado_por: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"))
    fecha: Mapped[datetime] = mapped_column(server_default=func.now())
