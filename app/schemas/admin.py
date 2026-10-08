"""Esquemas de administración (pueden incluir costo y ganancia; nunca se usan con clientes)."""

from datetime import datetime
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

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


class AlertaAdmin(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    tipo: str
    mensaje: str
    creada_en: datetime
    atendida_en: datetime | None
    atendida_por: int | None


class Panel(BaseModel):
    """Crédito real en VentasFF frente a lo que se debe a los clientes (RF-53, RN-10)."""

    # None si VentasFF no respondió (`error_proveedor` explica el motivo).
    credito_ventasff: Monto | None
    error_proveedor: str | None
    # Suma de saldo disponible + reservado de todos los clientes.
    saldos_clientes: Monto
    # credito_ventasff − saldos_clientes; negativo si el crédito no cubre los saldos.
    diferencia: Monto | None
    cubierto: bool | None
    pendientes_verificar: int
    ganancia_total: Monto
    alertas: list[AlertaAdmin]
    moneda: Literal["USD"] = "USD"


class ConfigAdmin(BaseModel):
    # RN-11: umbral de alerta de crédito bajo en USD.
    alerta_credito_min: Annotated[Decimal, Field(ge=0, max_digits=12, decimal_places=2)]


class PaqueteAdmin(BaseModel):
    """Paquete con costo y marcador de precio bajo costo (RF-12, RF-14)."""

    model_config = ConfigDict(from_attributes=True)

    paquete_id: int
    juego: str
    nombre: str
    diamantes: int | None
    precio_costo: Monto
    precio_venta: Monto | None
    activo: bool
    actualizado_en: datetime
    # precio_venta <= precio_costo (RF-12, RF-14).
    bajo_costo: bool = False


class CambioPaquete(BaseModel):
    precio_venta: Decimal | None = None
    activo: bool | None = None


class Catalogo(BaseModel):
    paquetes: list[PaqueteAdmin]
    # Resultado de la última sincronización (fecha, contadores o error), si hubo.
    ultima_sincronizacion: dict | None

