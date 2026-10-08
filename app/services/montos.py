"""Validación común de montos: Decimal exacto con 2 decimales (RNF-04)."""

from decimal import Decimal

CENTAVO = Decimal("0.01")
# Máximo de NUMERIC(12,2).
MONTO_MAXIMO = Decimal("9999999999.99")


class MontoInvalido(ValueError):
    pass


def normalizar_monto(monto: Decimal, *, con_signo: bool = False) -> Decimal:
    """Devuelve el monto con 2 decimales o lanza `MontoInvalido`.

    Sin `con_signo` exige monto > 0; con `con_signo` admite negativos pero no 0.
    """
    # bool es subclase de int, no de Decimal; float e int se rechazan.
    if not isinstance(monto, Decimal) or not monto.is_finite():
        raise MontoInvalido("El monto debe ser un Decimal finito")
    if monto != monto.quantize(CENTAVO):
        raise MontoInvalido("El monto admite como máximo 2 decimales")
    if abs(monto) > MONTO_MAXIMO:
        raise MontoInvalido("El monto excede el máximo permitido")
    if con_signo and monto == 0:
        raise MontoInvalido("El ajuste no puede ser 0")
    if not con_signo and monto <= 0:
        raise MontoInvalido("El monto debe ser mayor que 0")
    return monto.quantize(CENTAVO)
