"""Pruebas del enmascarado de secretos en logs (RNF-05)."""

import io
import logging
import uuid

import pytest

from app.config import cargar_configuracion
from app.logs import (
    MASCARA,
    FormateadorSeguro,
    configurar_logs,
    enmascarar,
    secretos_de_configuracion,
)

CLAVE = "rv_c_clave_de_prueba_123"


@pytest.fixture
def captura():
    """Logger aislado con un manejador seguro que escribe en memoria."""
    flujo = io.StringIO()
    manejador = logging.StreamHandler(flujo)
    manejador.setFormatter(FormateadorSeguro([CLAVE], "%(levelname)s %(message)s"))
    logger = logging.getLogger(f"test_logs.{uuid.uuid4().hex}")
    logger.setLevel(logging.DEBUG)
    logger.propagate = False
    logger.addHandler(manejador)
    try:
        yield logger, flujo
    finally:
        logger.removeHandler(manejador)


@pytest.fixture
def raiz_restaurada():
    """Guarda y restaura los manejadores y el nivel del logger raíz."""
    raiz = logging.getLogger()
    manejadores = list(raiz.handlers)
    nivel = raiz.level
    for manejador in manejadores:
        raiz.removeHandler(manejador)
    try:
        yield raiz
    finally:
        for manejador in list(raiz.handlers):
            raiz.removeHandler(manejador)
        for manejador in manejadores:
            raiz.addHandler(manejador)
        raiz.setLevel(nivel)


def test_enmascarar_reemplaza_secreto_y_bearer():
    texto = f"clave {CLAVE} y Bearer abc.def-123 fin"
    assert enmascarar(texto, [CLAVE]) == f"clave {MASCARA} y Bearer {MASCARA} fin"


def test_enmascarar_bearer_sin_lista_de_secretos():
    texto = "cabeceras: {'Authorization': 'bearer tok_xyz_987'}"
    assert enmascarar(texto, []) == f"cabeceras: {{'Authorization': 'Bearer {MASCARA}'}}"


def test_enmascarar_ignora_secretos_vacios_y_none():
    texto = "texto sin cambios"
    assert enmascarar(texto, ["", None]) == texto  # type: ignore[list-item]


def test_enmascarar_secreto_mas_corto_dentro_de_otro():
    corto = "rv_c_clave"
    largo = CLAVE
    texto = f"usa {largo} aquí"
    # El orden de la lista no importa: se sustituye primero el más largo.
    assert enmascarar(texto, [corto, largo]) == f"usa {MASCARA} aquí"
    assert enmascarar(texto, [largo, corto]) == f"usa {MASCARA} aquí"


def test_mensaje_con_argumentos_porcentuales(captura):
    logger, flujo = captura
    logger.info("clave recibida: %s", CLAVE)
    salida = flujo.getvalue()
    assert CLAVE not in salida
    assert MASCARA in salida


def test_mensaje_f_string(captura):
    logger, flujo = captura
    logger.warning(f"la API respondió con la clave {CLAVE}")
    salida = flujo.getvalue()
    assert CLAVE not in salida
    assert MASCARA in salida


def test_traceback_con_clave_en_el_mensaje_de_la_excepcion(captura):
    logger, flujo = captura
    try:
        raise ValueError(f"rechazada la clave {CLAVE}")
    except ValueError:
        logger.exception("fallo al llamar a VentasFF")
    salida = flujo.getvalue()
    assert "Traceback" in salida
    assert "ValueError" in salida
    assert CLAVE not in salida
    assert MASCARA in salida


def test_repr_de_diccionario_con_bearer_no_listado(captura):
    logger, flujo = captura
    otro_token = "otro-token-no-listado-987"
    logger.info("%r", {"Authorization": f"Bearer {otro_token}"})
    salida = flujo.getvalue()
    assert otro_token not in salida
    assert f"Bearer {MASCARA}" in salida


def test_secreto_que_contiene_otro_secreto_mas_corto():
    formateador = FormateadorSeguro(["rv_c_clave", CLAVE], "%(message)s")
    registro = logging.LogRecord("x", logging.INFO, __file__, 1, f"v={CLAVE}", None, None)
    salida = formateador.format(registro)
    assert salida == f"v={MASCARA}"


def test_secretos_de_configuracion():
    config = cargar_configuracion(
        ventasff_api_key=CLAVE,
        database_url="postgresql+psycopg://u:clave_bd_x@h:5432/d",
        secret_key="s" * 32,
        cookie_secure=False,
        test_database_url=None,
    )
    secretos = secretos_de_configuracion(config)
    assert CLAVE in secretos
    assert "s" * 32 in secretos
    assert "clave_bd_x" in secretos
    assert None not in secretos
    assert "" not in secretos


def test_configurar_logs_es_idempotente(raiz_restaurada):
    config = cargar_configuracion(
        ventasff_api_key=CLAVE,
        database_url="postgresql+psycopg://u:clave_bd_x@h:5432/d",
        secret_key="s" * 32,
        cookie_secure=False,
        test_database_url="postgresql+psycopg://u:clave_test_y@h:5432/t",
    )
    configurar_logs(config)
    configurar_logs(config)

    marcados = [
        h for h in raiz_restaurada.handlers if getattr(h, "_ffmovil_registro_seguro", False)
    ]
    assert len(marcados) == 1
    assert isinstance(marcados[0].formatter, FormateadorSeguro)
    assert raiz_restaurada.level == logging.INFO


def test_configurar_logs_aplica_formateador_a_uvicorn(raiz_restaurada):
    config = cargar_configuracion(
        ventasff_api_key=CLAVE,
        database_url="postgresql+psycopg://u:clave_bd_x@h:5432/d",
        secret_key="s" * 32,
        cookie_secure=False,
    )
    logger_uvicorn = logging.getLogger("uvicorn.access")
    manejador = logging.StreamHandler(io.StringIO())
    logger_uvicorn.addHandler(manejador)
    try:
        configurar_logs(config)
        assert isinstance(manejador.formatter, FormateadorSeguro)
    finally:
        logger_uvicorn.removeHandler(manejador)


def test_clave_bd_codificada_en_url():
    config = cargar_configuracion(
        ventasff_api_key="rv_c_x",
        database_url="postgresql+psycopg://u:cl%40ve%2Fbd@h:5432/d",
        secret_key="s" * 40,
        cookie_secure=False,
        test_database_url=None,
    )
    secretos = secretos_de_configuracion(config)
    assert "cl@ve/bd" in secretos
    texto = enmascarar("url postgresql+psycopg://u:cl%40ve%2Fbd@h:5432/d", secretos)
    assert "cl%40ve%2Fbd" not in texto
