from datetime import datetime

from sqlalchemy import BigInteger, CheckConstraint, ForeignKey, Identity, Text, func
from sqlalchemy.dialects.postgresql import INET, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, valores_sql

ROLES = ("admin", "cliente")


class Usuario(Base):
    __tablename__ = "usuarios"
    __table_args__ = (CheckConstraint(f"rol IN ({valores_sql(ROLES)})", name="rol"),)

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    usuario: Mapped[str] = mapped_column(Text, unique=True)
    hash_password: Mapped[str] = mapped_column(Text)
    rol: Mapped[str] = mapped_column(Text)
    debe_cambiar_clave: Mapped[bool] = mapped_column(server_default="true")
    activo: Mapped[bool] = mapped_column(server_default="true")
    creado_en: Mapped[datetime] = mapped_column(server_default=func.now())
    ultimo_login: Mapped[datetime | None]


class Auditoria(Base):
    """Acciones del admin (RF-55)."""

    __tablename__ = "auditoria"

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    usuario_id: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"))
    accion: Mapped[str] = mapped_column(Text)
    detalle: Mapped[dict | None] = mapped_column(JSONB)
    ip: Mapped[str | None] = mapped_column(INET)
    fecha: Mapped[datetime] = mapped_column(server_default=func.now(), index=True)
