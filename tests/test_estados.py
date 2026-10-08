"""Máquina de estados de pedidos (spec sección 7, RN-04). Sin base de datos."""

import itertools

import pytest

from app.services.estados import (
    ESTADOS_FINALES,
    ETIQUETAS_CLIENTE,
    Estado,
    TransicionInvalida,
    transiciones_desde,
    validar_transicion,
)

CREADO = Estado.CREADO
PROCESANDO = Estado.PROCESANDO
EXITOSO = Estado.EXITOSO
FALLIDO = Estado.FALLIDO
PENDIENTE = Estado.PENDIENTE_VERIFICAR

# Tabla explícita de transiciones válidas: (origen, destino) -> requiere admin.
# Un par ausente de esta tabla es inválido siempre.
TRANSICIONES_AUTOMATICAS = {
    (CREADO, PROCESANDO),
    (PROCESANDO, EXITOSO),
    (PROCESANDO, FALLIDO),
    (PROCESANDO, PENDIENTE),
}
TRANSICIONES_ADMIN = {
    (PENDIENTE, EXITOSO),
    (PENDIENTE, FALLIDO),
}


def test_estado_valores_son_nombres_en_mayusculas():
    assert {e.value for e in Estado} == {
        "CREADO",
        "PROCESANDO",
        "EXITOSO",
        "FALLIDO",
        "PENDIENTE_VERIFICAR",
    }
    assert all(isinstance(e, str) for e in Estado)


def test_estados_finales():
    assert ESTADOS_FINALES == frozenset({EXITOSO, FALLIDO})


@pytest.mark.parametrize(
    ("estado", "etiqueta"),
    [
        (CREADO, "Procesando"),
        (PROCESANDO, "Procesando"),
        (EXITOSO, "Exitoso"),
        (FALLIDO, "Fallido"),
        (PENDIENTE, "En revisión"),
    ],
)
def test_etiquetas_cliente(estado, etiqueta):
    assert ETIQUETAS_CLIENTE[estado] == etiqueta


def test_etiquetas_cliente_cubren_todos_los_estados():
    assert set(ETIQUETAS_CLIENTE) == set(Estado)


@pytest.mark.parametrize("por_admin", [False, True])
@pytest.mark.parametrize(
    ("origen", "destino"),
    list(itertools.product(Estado, Estado)),
)
def test_matriz_completa_de_transiciones(origen, destino, por_admin):
    esperada = (origen, destino) in TRANSICIONES_AUTOMATICAS or (
        por_admin and (origen, destino) in TRANSICIONES_ADMIN
    )
    if esperada:
        assert validar_transicion(origen, destino, por_admin=por_admin) is destino
    else:
        with pytest.raises(TransicionInvalida) as info:
            validar_transicion(origen, destino, por_admin=por_admin)
        assert info.value.actual is origen
        assert info.value.nuevo is destino


@pytest.mark.parametrize("por_admin", [False, True])
@pytest.mark.parametrize("origen", list(Estado))
def test_transiciones_desde_coincide_con_la_tabla(origen, por_admin):
    esperadas = {d for (o, d) in TRANSICIONES_AUTOMATICAS if o is origen}
    if por_admin:
        esperadas |= {d for (o, d) in TRANSICIONES_ADMIN if o is origen}
    assert transiciones_desde(origen, por_admin=por_admin) == frozenset(esperadas)


@pytest.mark.parametrize("estado", sorted(ESTADOS_FINALES, key=lambda e: e.value))
@pytest.mark.parametrize("por_admin", [False, True])
def test_estados_finales_no_tienen_salida(estado, por_admin):
    assert transiciones_desde(estado, por_admin=por_admin) == frozenset()


def test_pendiente_verificar_solo_sale_con_admin():
    assert transiciones_desde(PENDIENTE) == frozenset()
    assert transiciones_desde(PENDIENTE, por_admin=True) == frozenset({EXITOSO, FALLIDO})


def test_no_hay_transicion_hacia_creado():
    for origen in Estado:
        for por_admin in (False, True):
            assert CREADO not in transiciones_desde(origen, por_admin=por_admin)


def test_pendiente_verificar_no_se_reintenta_automaticamente():
    with pytest.raises(TransicionInvalida):
        validar_transicion(PENDIENTE, EXITOSO)
    with pytest.raises(TransicionInvalida):
        validar_transicion(PENDIENTE, FALLIDO)


def test_acepta_strings_y_devuelve_estado():
    resultado = validar_transicion("CREADO", "PROCESANDO")
    assert resultado is PROCESANDO
    assert isinstance(resultado, Estado)
    assert validar_transicion("PENDIENTE_VERIFICAR", "EXITOSO", por_admin=True) is EXITOSO


def test_mezcla_de_str_y_estado():
    assert validar_transicion(PROCESANDO, "FALLIDO") is FALLIDO
    assert validar_transicion("PROCESANDO", FALLIDO) is FALLIDO


def test_string_desconocido_lanza_transicion_invalida():
    with pytest.raises(TransicionInvalida) as info:
        validar_transicion("DESCONOCIDO", "PROCESANDO")
    assert info.value.actual == "DESCONOCIDO"
    assert info.value.nuevo == "PROCESANDO"

    with pytest.raises(TransicionInvalida):
        validar_transicion(CREADO, "NO_EXISTE")


def test_minusculas_no_son_estados_validos():
    with pytest.raises(TransicionInvalida):
        validar_transicion("creado", "PROCESANDO")


def test_mensaje_nombra_ambos_estados():
    with pytest.raises(TransicionInvalida) as info:
        validar_transicion(EXITOSO, PROCESANDO)
    mensaje = str(info.value)
    assert "EXITOSO" in mensaje
    assert "PROCESANDO" in mensaje


def test_error_conserva_atributos_con_str():
    with pytest.raises(TransicionInvalida) as info:
        validar_transicion("EXITOSO", "FALLIDO")
    assert info.value.actual == "EXITOSO"
    assert info.value.nuevo == "FALLIDO"
    assert isinstance(info.value, Exception)
