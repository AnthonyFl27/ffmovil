"""T-022: RATE_LIMITED y Retry-After (RN-07)."""

from datetime import UTC, datetime, timedelta
from email.utils import format_datetime

import httpx
import pytest
import respx

from app.services.ventasff_client import (
    PAUSA_MAXIMA,
    URL_BASE,
    ClienteVentasFF,
    ErrorAPI,
    segundos_retry_after,
)
from tests.fake_ventasff import SimuladorVentasFF

BASE = "http://simulador/api/reseller"
AHORA = datetime(2026, 10, 8, 12, 0, tzinfo=UTC)


@pytest.mark.parametrize(
    ("valor", "esperado"),
    [
        ("5", 5.0),
        (" 2.5 ", 2.5),
        ("0", 0.0),
        ("-3", 0.0),
        ("999", PAUSA_MAXIMA),
        (None, PAUSA_MAXIMA),
        ("", PAUSA_MAXIMA),
        ("pronto", PAUSA_MAXIMA),
        ("nan", PAUSA_MAXIMA),
        ("inf", PAUSA_MAXIMA),
        (format_datetime(AHORA + timedelta(seconds=10), usegmt=True), 10.0),
        (format_datetime(AHORA - timedelta(seconds=10), usegmt=True), 0.0),
    ],
)
def test_interpretar_retry_after(valor, esperado):
    assert segundos_retry_after(valor, ahora=AHORA) == esperado


class RelojFalso:
    def __init__(self):
        self.ahora = 1000.0
        self.esperas: list[float] = []

    def __call__(self) -> float:
        return self.ahora

    async def dormir(self, segundos: float) -> None:
        self.esperas.append(segundos)
        self.ahora += segundos


def cliente_simulado(sim: SimuladorVentasFF, reloj: RelojFalso) -> ClienteVentasFF:
    return ClienteVentasFF(
        sim.api_key, BASE, transport=sim.transporte(), reloj=reloj, dormir=reloj.dormir
    )


async def test_rate_limited_pausa_sin_reintentar():
    sim = SimuladorVentasFF(escenario_recarga="RATE_LIMITED", retry_after=7)
    reloj = RelojFalso()
    async with cliente_simulado(sim, reloj) as cliente:
        with pytest.raises(ErrorAPI) as error:
            await cliente.recargar(1, "75807448")
        assert (error.value.code, error.value.estado_http) == ("RATE_LIMITED", 429)
        assert error.value.retry_after == 7.0
        # No reintenta por su cuenta: una sola recarga enviada.
        assert [p for p in sim.peticiones if p[1].endswith("recargar.php")] == [
            ("POST", "/api/reseller/recargar.php")
        ]
        assert reloj.esperas == []

        # La siguiente petición espera el plazo antes de enviarse.
        reloj.ahora += 2
        await cliente.saldo()
        assert reloj.esperas == [5.0]

        # Pasado el plazo, ya no espera.
        await cliente.saldo()
        assert reloj.esperas == [5.0]


async def test_sin_pausa_si_el_plazo_ya_paso():
    sim = SimuladorVentasFF(escenario_recarga="RATE_LIMITED", retry_after=3)
    reloj = RelojFalso()
    async with cliente_simulado(sim, reloj) as cliente:
        with pytest.raises(ErrorAPI):
            await cliente.recargar(1, "75807448")
        reloj.ahora += 10
        await cliente.saldo()
    assert reloj.esperas == []


async def test_429_sin_cabecera_usa_pausa_maxima():
    reloj = RelojFalso()
    with respx.mock(base_url=URL_BASE) as api:
        api.get("/saldo.php").mock(
            return_value=httpx.Response(
                429, content=b'{"success":false,"error":"Tope","code":"RATE_LIMITED"}'
            )
        )
        async with ClienteVentasFF("rv_c_x", reloj=reloj, dormir=reloj.dormir) as cliente:
            with pytest.raises(ErrorAPI) as error:
                await cliente.saldo()
    assert error.value.retry_after == PAUSA_MAXIMA


async def test_otros_errores_no_pausan():
    sim = SimuladorVentasFF(escenario_recarga="BUSY")
    reloj = RelojFalso()
    async with cliente_simulado(sim, reloj) as cliente:
        with pytest.raises(ErrorAPI) as error:
            await cliente.recargar(1, "75807448")
        assert error.value.retry_after is None
        await cliente.saldo()
    assert reloj.esperas == []
