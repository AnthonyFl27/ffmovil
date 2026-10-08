"""Esquemas de administración (pueden incluir costo y ganancia; nunca se usan con clientes)."""

from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict

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


class MovimientoAdmin(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    usuario_id: int
    tipo: str
    monto: Monto
    saldo_disponible_resultante: Monto
    saldo_reservado_resultante: Monto
    nota: str | None
    fecha: datetime


class PedidoAdmin(BaseModel):
    """Pedido con costo y ganancia (RF-50, RF-51, RF-54)."""

    id: int
    codigo: str
    fecha: datetime
    actualizado_en: datetime
    usuario_id: int
    usuario: str
    paquete_id: int
    paquete: str
    player_id: str
    nickname: str | None
    precio_venta: Monto
    precio_costo: Monto
    # precio_venta − precio_costo, solo en pedidos EXITOSO (RF-54).
    ganancia: Monto | None
    estado: str
    referencia: str | None
    error: str | None
    error_code: str | None


class TotalesGanancia(BaseModel):
    """Totales de los pedidos EXITOSO que cumplen los filtros (RF-54)."""

    exitosos: int
    venta: Monto
    costo: Monto
    ganancia: Monto


class ListaPedidosAdmin(BaseModel):
    pedidos: list[PedidoAdmin]
    total: int
    pagina: int
    por_pagina: int
    totales: TotalesGanancia


class EventoPedido(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    estado_anterior: str | None
    estado_nuevo: str
    detalle: str | None
    creado_por: int | None
    fecha: datetime


class DetallePedidoAdmin(PedidoAdmin):
    eventos: list[EventoPedido]


class Resolucion(BaseModel):
    """Resolución manual de PENDIENTE_VERIFICAR (RF-52)."""

    resultado: Literal["exitoso", "fallido"]
    nota: str
    referencia: str | None = None

