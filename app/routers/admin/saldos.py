"""Abonos y ajustes de saldo por el admin (RF-40, RF-41, RF-42, RF-55)."""

from fastapi import APIRouter, HTTPException, Request, status

from app.routers.dependencias import Admin, Bd, ip_cliente
from app.schemas.admin import MovimientoAdmin, MovimientoSaldo
from app.services import auditoria, ledger
from app.services.ledger import CuentaInexistente, ErrorLedger

router = APIRouter(prefix="/saldos")

MENSAJE_SIN_CUENTA = "El usuario no existe o no tiene cuenta de saldo."


async def _aplicar(tipo: str, usuario_id: int, datos: MovimientoSaldo, request, actual, bd):
    operacion = ledger.abonar if tipo == "abono" else ledger.ajustar
    try:
        movimiento = await operacion(
            bd, usuario_id, datos.monto, nota=datos.nota, creado_por=actual.usuario_id
        )
    except CuentaInexistente:
        await bd.rollback()
        raise HTTPException(status.HTTP_404_NOT_FOUND, MENSAJE_SIN_CUENTA) from None
    except ErrorLedger as error:
        await bd.rollback()
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(error)) from None
    auditoria.registrar(
        bd,
        actual.usuario_id,
        tipo,
        {
            "usuario_id": usuario_id,
            "movimiento_id": movimiento.id,
            "monto": f"{movimiento.monto:.2f}",
            "nota": movimiento.nota,
        },
        ip_cliente(request),
    )
    await bd.commit()
    await bd.refresh(movimiento)
    return MovimientoAdmin.model_validate(movimiento)


@router.post(
    "/{usuario_id}/abono", response_model=MovimientoAdmin, status_code=status.HTTP_201_CREATED
)
async def abonar(usuario_id: int, datos: MovimientoSaldo, request: Request, actual: Admin, bd: Bd):
    """Abono con nota obligatoria: método de pago y referencia (RF-40)."""
    return await _aplicar("abono", usuario_id, datos, request, actual, bd)


@router.post(
    "/{usuario_id}/ajuste", response_model=MovimientoAdmin, status_code=status.HTTP_201_CREATED
)
async def ajustar(usuario_id: int, datos: MovimientoSaldo, request: Request, actual: Admin, bd: Bd):
    """Ajuste positivo o negativo con nota obligatoria; nunca deja saldo negativo (RF-41, RN-01)."""
    return await _aplicar("ajuste", usuario_id, datos, request, actual, bd)
