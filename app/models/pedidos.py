from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    ForeignKey,
    Identity,
    Index,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, valores_sql

# Estados del pedido (spec sec. 7); las transiciones las valida app/services/estados.py.
ESTADOS_PEDIDO = ("CREADO", "PROCESANDO", "EXITOSO", "FALLIDO", "PENDIENTE_VERIFICAR")


class Pedido(Base):
    """Recarga solicitada por un cliente (RF-20 a RF-31).

    Los precios se congelan al crear el pedido (RN-02, RF-14).
    """

    __tablename__ = "pedidos"
    __table_args__ = (
        CheckConstraint(f"estado IN ({valores_sql(ESTADOS_PEDIDO)})", name="estado"),
        # RF-27: Player ID numérico de 4 a 20 dígitos.
        CheckConstraint("player_id ~ '^[0-9]{4,20}$'", name="player_id_formato"),
        CheckConstraint("precio_venta > 0", name="precio_venta_positivo"),
        CheckConstraint("precio_costo >= 0", name="precio_costo_no_negativo"),
        CheckConstraint("length(token_idempotencia) > 0", name="token_no_vacio"),
        # RF-25: un reenvío con el mismo token no crea otro pedido.
        UniqueConstraint("usuario_id", "token_idempotencia", name="uq_pedidos_usuario_token"),
        Index("ix_pedidos_usuario_id_creado_en", "usuario_id", "creado_en"),
        Index("ix_pedidos_estado", "estado"),
        Index("ix_pedidos_referencia", "referencia"),
        Index("ix_pedidos_player_id", "player_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    # 'FF-000123', derivado del id tras insertar (RF-30).
    codigo: Mapped[str | None] = mapped_column(Text, unique=True)
    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"))
    paquete_id: Mapped[int] = mapped_column(ForeignKey("paquetes.paquete_id"))
    player_id: Mapped[str] = mapped_column(Text)
    nickname: Mapped[str | None] = mapped_column(Text)
    precio_costo: Mapped[Decimal]
    precio_venta: Mapped[Decimal]
    estado: Mapped[str] = mapped_column(Text)
    referencia: Mapped[str | None] = mapped_column(Text)
    error: Mapped[str | None] = mapped_column(Text)
    error_code: Mapped[str | None] = mapped_column(Text)
    token_idempotencia: Mapped[str] = mapped_column(Text)
    creado_en: Mapped[datetime] = mapped_column(server_default=func.now())
    actualizado_en: Mapped[datetime] = mapped_column(server_default=func.now())


class PedidoEvento(Base):
    """Historial de estados de un pedido (RF-51)."""

    __tablename__ = "pedido_eventos"

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    pedido_id: Mapped[int] = mapped_column(ForeignKey("pedidos.id"), index=True)
    estado_anterior: Mapped[str | None] = mapped_column(Text)
    estado_nuevo: Mapped[str] = mapped_column(Text)
    detalle: Mapped[str | None] = mapped_column(Text)
    # Admin que resolvió el pedido; NULL si fue el sistema.
    creado_por: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"))
    fecha: Mapped[datetime] = mapped_column(server_default=func.now())
