import pytest

from app.config import ErrorConfiguracion, cargar_configuracion

VARIABLES = {
    "VENTASFF_API_KEY": "rv_clave_de_prueba",
    "DATABASE_URL": "postgresql+psycopg://u:p@localhost:5432/bd",
    "SECRET_KEY": "x" * 48,
    "COOKIE_SECURE": "false",
}


@pytest.fixture
def entorno(monkeypatch):
    for nombre in [*VARIABLES, "TEST_DATABASE_URL"]:
        monkeypatch.delenv(nombre, raising=False)
    for nombre, valor in VARIABLES.items():
        monkeypatch.setenv(nombre, valor)
    return monkeypatch


def cargar():
    # _env_file=None: las pruebas no leen el .env real.
    return cargar_configuracion(_env_file=None)


def test_carga_completa(entorno):
    config = cargar()
    assert config.ventasff_api_key.get_secret_value() == "rv_clave_de_prueba"
    assert config.cookie_secure is False
    assert config.test_database_url is None


@pytest.mark.parametrize("variable", list(VARIABLES))
def test_falla_si_falta_variable(entorno, variable):
    entorno.delenv(variable)
    with pytest.raises(ErrorConfiguracion, match=variable):
        cargar()


@pytest.mark.parametrize("variable", ["VENTASFF_API_KEY", "DATABASE_URL", "SECRET_KEY"])
def test_falla_si_variable_vacia(entorno, variable):
    entorno.setenv(variable, "")
    with pytest.raises(ErrorConfiguracion, match=variable):
        cargar()


def test_secret_key_corta(entorno):
    entorno.setenv("SECRET_KEY", "corta")
    with pytest.raises(ErrorConfiguracion, match="SECRET_KEY"):
        cargar()


def test_cookie_secure_invalida(entorno):
    entorno.setenv("COOKIE_SECURE", "quizas")
    with pytest.raises(ErrorConfiguracion, match="COOKIE_SECURE"):
        cargar()


def test_error_no_expone_valores(entorno):
    entorno.delenv("DATABASE_URL")
    entorno.setenv("SECRET_KEY", "secreto-corto")
    with pytest.raises(ErrorConfiguracion) as error:
        cargar()
    mensaje = str(error.value)
    assert "secreto-corto" not in mensaje
    assert "rv_clave_de_prueba" not in mensaje


def test_repr_no_expone_secretos(entorno):
    config = cargar()
    texto = repr(config) + str(config.model_dump())
    assert "rv_clave_de_prueba" not in texto
    assert "x" * 48 not in texto
