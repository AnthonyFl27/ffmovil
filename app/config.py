"""Configuración de la aplicación leída de variables de entorno (o `.env`).

Los secretos se guardan como `SecretStr` para que no aparezcan al imprimir
o registrar la configuración (RNF-01, RNF-05).
"""

from functools import lru_cache

from pydantic import Field, SecretStr, ValidationError
from pydantic_settings import BaseSettings, SettingsConfigDict


class ErrorConfiguracion(RuntimeError):
    """La configuración está incompleta o es inválida."""


class Configuracion(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    ventasff_api_key: SecretStr = Field(min_length=1)
    database_url: SecretStr = Field(min_length=1)
    secret_key: SecretStr = Field(min_length=32)
    cookie_secure: bool
    # Solo la necesitan las pruebas (RNF-10); producción no la define.
    test_database_url: SecretStr | None = None


def _describir_errores(error: ValidationError) -> str:
    # Solo nombres de variables y motivo; nunca los valores recibidos.
    lineas = []
    for detalle in error.errors(include_input=False, include_url=False):
        variable = str(detalle["loc"][0]).upper() if detalle["loc"] else "?"
        vacia = (
            detalle["type"] in ("string_too_short", "too_short")
            and detalle.get("ctx", {}).get("min_length") == 1
        )
        motivo = "falta o está vacía" if detalle["type"] == "missing" or vacia else detalle["msg"]
        lineas.append(f"  - {variable}: {motivo}")
    return "\n".join(lineas)


def cargar_configuracion(**kwargs) -> Configuracion:
    try:
        return Configuracion(**kwargs)
    except ValidationError as error:
        raise ErrorConfiguracion(
            "Configuración inválida. Revisa el archivo .env (ver .env.example):\n"
            + _describir_errores(error)
        ) from None


@lru_cache
def obtener_configuracion() -> Configuracion:
    return cargar_configuracion()
