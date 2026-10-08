from datetime import datetime

from sqlalchemy import BigInteger, ForeignKey, Text, func
from sqlalchemy.dialects.postgresql import INET
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Sesion(Base):
    """Sesión iniciada por un usuario (RF-06, plan sec. 7).

    Solo se guarda el SHA-256 del token de la cookie, nunca el token.
    """

    __tablename__ = "sesiones"

    token_hash: Mapped[str] = mapped_column(Text, primary_key=True)
    usuario_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("usuarios.id", ondelete="CASCADE"), index=True
    )
    csrf: Mapped[str] = mapped_column(Text)
    ip: Mapped[str | None] = mapped_column(INET)
    creada_en: Mapped[datetime] = mapped_column(server_default=func.now())
    ultima_actividad: Mapped[datetime] = mapped_column(server_default=func.now())
