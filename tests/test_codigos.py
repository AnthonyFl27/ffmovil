"""Pruebas del código legible de pedido (RF-30)."""

import pytest

from app.services.codigos import codigo_pedido, id_desde_codigo


@pytest.mark.parametrize(
    ("pedido_id", "esperado"),
    [
        (1, "FF-000001"),
        (123, "FF-000123"),
        (999999, "FF-999999"),
        (1000000, "FF-1000000"),
        (1234567, "FF-1234567"),
    ],
)
def test_codigo_pedido_ejemplos(pedido_id: int, esperado: str) -> None:
    assert codigo_pedido(pedido_id) == esperado


def test_codigo_pedido_ids_distintos_dan_codigos_distintos() -> None:
    ids = list(range(1, 2001)) + [10**6, 10**6 + 1, 12345678, 99999999]
    codigos = [codigo_pedido(i) for i in ids]
    assert len(set(codigos)) == len(ids)


def test_ida_y_vuelta() -> None:
    ids = list(range(1, 2001)) + [999999, 1000000, 1234567, 10**9]
    for i in ids:
        assert id_desde_codigo(codigo_pedido(i)) == i


def test_id_desde_codigo_acepta_espacios_y_minusculas() -> None:
    assert id_desde_codigo("ff-000123") == 123
    assert id_desde_codigo("  FF-000123  ") == 123
    assert id_desde_codigo("\tff-1000000\n") == 1000000


@pytest.mark.parametrize("pedido_id", [0, -1, True, False, "5", None, 1.0])
def test_codigo_pedido_rechaza_entradas_invalidas(pedido_id: object) -> None:
    with pytest.raises(ValueError):
        codigo_pedido(pedido_id)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "codigo",
    [
        "FF-12",
        "FF-00012a",
        "XX-000123",
        "FF-0000123",
        "",
        "FF-000000",
        "FF-000",
        "FF-",
        "123456",
        "FF 000123",
        "FF-00012 3",
        "FF-01234567",
    ],
)
def test_id_desde_codigo_rechaza_codigos_invalidos(codigo: str) -> None:
    assert id_desde_codigo(codigo) is None


@pytest.mark.parametrize("entrada", [None, 123, 5, b"FF-000123", ["FF-000123"]])
def test_id_desde_codigo_no_str_devuelve_none(entrada: object) -> None:
    assert id_desde_codigo(entrada) is None  # type: ignore[arg-type]
