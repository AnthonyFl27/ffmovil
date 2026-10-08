from datetime import datetime

from sqlalchemy import BigInteger, CheckConstraint, ForeignKey, Identity, Index, Text, func, text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, valores_sql

TIPOS_ALERTA = ("credito_bajo", "sin_credito", "cuenta")


class Alerta(Base):
    """Alerta visible para el admin (RN-08, RN-11)."""

    __tablename__ = "alertas"
    __table_args__ = (
        CheckConstraint(f"tipo IN ({valores_sql(TIPOS_ALERTA)})", name="tipo"),
        # Una sola alerta activa (no atendida) por tipo.
        Index(
            "uq_alertas_tipo_activa",
            "tipo",
            unique=True,
            postgresql_where=text("atendida_en IS NULL"),
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    tipo: Mapped[str] = mapped_column(Text)
    mensaje: Mapped[str] = mapped_column(Text)
    creada_en: Mapped[datetime] = mapped_column(server_default=func.now())
    atendida_en: Mapped[datetime | None]
    atendida_por: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"))
