"""Esquemas de administración (pueden incluir costo y ganancia; nunca se usan con clientes)."""

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel

from app.schemas.cliente import Monto


class UsuarioAdmin(BaseModel):
    id: int
    usuario: str
    rol: str
    activo: bool
    debe_cambiar_clave: bool
    creado_en: datetime
    ultimo_login: datetime | None
    # Solo clientes; los admins no tienen cuenta de saldo.
    saldo_disponible: Monto | None = None
    saldo_reservado: Monto | None = None


class NuevoUsuario(BaseModel):
    usuario: str


class UsuarioConClave(BaseModel):
    """Respuesta de crear o resetear: la clave temporal se muestra una sola vez (RF-02)."""

    usuario: UsuarioAdmin
    clave_temporal: str


class MovimientoSaldo(BaseModel):
    monto: Decimal
    nota: str
