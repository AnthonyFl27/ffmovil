"""Panel del admin, alertas y configuración (RF-53, RF-54, RN-10, RN-11, RF-55)."""

import logging
from decimal import Decimal

from fastapi import APIRouter, HTTPException, Request, status
from sqlalchemy import func, select

from app.models import Config, Pedido, Saldo
from app.routers.dependencias import Admin, Bd, ip_cliente
from app.schemas.admin import AlertaAdmin, ConfigAdmin, Panel
from app.services import alertas, auditoria
from app.services.alertas import CLAVE_UMBRAL, AlertaInexistente
from app.services.estados import Estado
from app.services.ventasff_client import ErrorVentasFF

logger = logging.getLogger(__name__)

router = APIRouter()

MENSAJE_PROVEEDOR = "No se pudo consultar el saldo en VentasFF."


@router.get("/panel", response_model=Panel)
async def panel(request: Request, bd: Bd):
    """Saldo real en VentasFF frente a la suma de saldos de clientes (RF-53, RN-10)."""
    credito = error = None
    try:
        credito = (await request.app.state.ventasff.saldo()).credito
    except ErrorVentasFF as fallo:
        logger.warning("Panel: saldo.php falló: %s", type(fallo).__name__)
        error = MENSAJE_PROVEEDOR
    if credito is not None:
        # RN-11 (a): el panel también detecta el crédito bajo.
        await alertas.comprobar_credito(bd, credito)
        await bd.commit()

    saldos, pendientes, ganancia = (
        await bd.execute(
            select(
                select(
                    func.coalesce(func.sum(Saldo.saldo_disponible + Saldo.saldo_reservado), 0)
                ).scalar_subquery(),
                select(func.count())
                .select_from(Pedido)
                .where(Pedido.estado == Estado.PENDIENTE_VERIFICAR)
                .scalar_subquery(),
                select(func.coalesce(func.sum(Pedido.precio_venta - Pedido.precio_costo), 0))
                .where(Pedido.estado == Estado.EXITOSO)
                .scalar_subquery(),
            )
        )
    ).one()
    activas = await alertas.alertas_activas(bd)
    return Panel(
        credito_ventasff=credito,
        error_proveedor=error,
        saldos_clientes=saldos,
        diferencia=credito - saldos if credito is not None else None,
        cubierto=credito >= saldos if credito is not None else None,
        saldo_por_cubrir=max(saldos - credito, Decimal("0.00")) if credito is not None else None,
        pendientes_verificar=pendientes,
        ganancia_total=ganancia,
        alertas=[AlertaAdmin.model_validate(a) for a in activas],
    )


@router.get("/alertas", response_model=list[AlertaAdmin])
async def listar_alertas(bd: Bd):
    """Alertas activas, las más recientes primero (RN-11)."""
    return [AlertaAdmin.model_validate(a) for a in await alertas.alertas_activas(bd)]


@router.post("/alertas/{alerta_id}/atender", response_model=AlertaAdmin)
async def atender(alerta_id: int, request: Request, actual: Admin, bd: Bd):
    """Marca la alerta como atendida; queda en auditoría (RN-11, RF-55)."""
    try:
        alerta = await alertas.atender_alerta(
            bd, alerta_id, admin_id=actual.usuario_id, ip=ip_cliente(request)
        )
    except AlertaInexistente:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Alerta no encontrada.") from None
    await bd.commit()
    return AlertaAdmin.model_validate(alerta)


@router.get("/config", response_model=ConfigAdmin)
async def ver_config(bd: Bd):
    return ConfigAdmin(alerta_credito_min=await alertas.umbral_credito(bd))


@router.put("/config", response_model=ConfigAdmin)
async def cambiar_config(datos: ConfigAdmin, request: Request, actual: Admin, bd: Bd):
    """Cambia el umbral de crédito bajo (RN-11); queda en auditoría (RF-55)."""
    anterior = await alertas.umbral_credito(bd)
    nuevo = f"{datos.alerta_credito_min:.2f}"
    await bd.merge(Config(clave=CLAVE_UMBRAL, valor=nuevo))
    auditoria.registrar(
        bd,
        actual.usuario_id,
        "cambiar_config",
        {"clave": CLAVE_UMBRAL, "anterior": f"{anterior:.2f}", "nuevo": nuevo},
        ip_cliente(request),
    )
    await bd.commit()
    return ConfigAdmin(alerta_credito_min=datos.alerta_credito_min)
