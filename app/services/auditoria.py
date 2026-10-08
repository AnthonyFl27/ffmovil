"""Registro de acciones del admin (RF-55). No hace commit: va en la transacción de la acción."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Auditoria


def registrar(
    sesion: AsyncSession, admin_id: int, accion: str, detalle: dict, ip: str | None
) -> None:
    """Añade la fila de auditoría. `detalle` nunca lleva contraseñas ni secretos (RNF-05)."""
    sesion.add(Auditoria(usuario_id=admin_id, accion=accion, detalle=detalle, ip=ip))
