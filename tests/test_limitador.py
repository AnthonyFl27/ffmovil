"""Pruebas del limitador de tasa en ventana deslizante (RN-07)."""

import asyncio

import pytest

from app.services.limitador import (
    PETICIONES_POR_MINUTO,
    RECARGAS_POR_MINUTO,
    LimitadorTasa,
)


class RelojFalso:
    """Reloj controlado por la prueba. `dormir` avanza el reloj sin esperar de verdad."""

    def __init__(self, inicio: float = 0.0) -> None:
        self.t = inicio
        self.esperas: list[float] = []

    def __call__(self) -> float:
        return self.t

    async def dormir(self, segundos: float) -> None:
        self.esperas.append(segundos)
        self.t += segundos
        # Cede el control al event loop como lo haría un sleep real.
        await asyncio.sleep(0)


async def test_primeras_adquisiciones_no_esperan() -> None:
    reloj = RelojFalso()
    limitador = LimitadorTasa(3, 60.0, reloj=reloj, dormir=reloj.dormir)

    esperas = [await limitador.adquirir() for _ in range(3)]

    assert esperas == [0.0, 0.0, 0.0]
    assert reloj.esperas == []


async def test_espera_hasta_que_sale_la_mas_antigua() -> None:
    reloj = RelojFalso()
    limitador = LimitadorTasa(3, 60.0, reloj=reloj, dormir=reloj.dormir)

    for instante in (0.0, 10.0, 20.0):
        reloj.t = instante
        assert await limitador.adquirir() == 0.0

    reloj.t = 25.0
    esperado = await limitador.adquirir()

    assert esperado == 35.0
    assert reloj.esperas == [35.0]
    assert reloj.t == 60.0


async def test_ventana_se_desliza_sobre_varias_ventanas() -> None:
    reloj = RelojFalso()
    limitador = LimitadorTasa(2, 10.0, reloj=reloj, dormir=reloj.dormir)

    esperas = [await limitador.adquirir(), await limitador.adquirir()]
    # Tercera: espera hasta t=10, cuando salen ambas marcas de t=0.
    esperas.append(await limitador.adquirir())
    # Cuarta: en t=10 todavía hay cupo (solo entró una nueva marca en t=10).
    esperas.append(await limitador.adquirir())
    # Quinta: hay que esperar hasta t=20.
    esperas.append(await limitador.adquirir())

    assert esperas == [0.0, 0.0, 10.0, 0.0, 10.0]
    assert reloj.t == 20.0
    assert reloj.esperas == [10.0, 10.0]


async def test_disponibles_refleja_el_cupo_y_se_recupera() -> None:
    reloj = RelojFalso()
    limitador = LimitadorTasa(3, 60.0, reloj=reloj, dormir=reloj.dormir)

    assert limitador.disponibles() == 3

    await limitador.adquirir()
    await limitador.adquirir()
    assert limitador.disponibles() == 1

    await limitador.adquirir()
    assert limitador.disponibles() == 0

    reloj.t = 59.9
    assert limitador.disponibles() == 0

    reloj.t = 60.0
    assert limitador.disponibles() == 3


async def test_concurrencia_nunca_supera_el_maximo_en_una_ventana() -> None:
    reloj = RelojFalso()
    maximo, ventana = 3, 60.0
    limitador = LimitadorTasa(maximo, ventana, reloj=reloj, dormir=reloj.dormir)
    instantes: list[float] = []

    async def llamar() -> None:
        await limitador.adquirir()
        instantes.append(reloj())

    await asyncio.gather(*(llamar() for _ in range(10)))

    assert len(instantes) == 10
    for t in instantes:
        dentro = [o for o in instantes if t - ventana < o <= t]
        assert len(dentro) <= maximo


@pytest.mark.parametrize(
    ("maximo", "ventana"),
    [(0, 60.0), (-1, 60.0), (3, 0.0), (3, -5.0)],
)
def test_argumentos_invalidos_lanzan_value_error(maximo: int, ventana: float) -> None:
    with pytest.raises(ValueError):
        LimitadorTasa(maximo, ventana)


def test_constantes_quedan_por_debajo_de_los_topes_del_proveedor() -> None:
    assert RECARGAS_POR_MINUTO < 10
    assert PETICIONES_POR_MINUTO < 60
