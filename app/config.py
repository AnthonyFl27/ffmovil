"""Configuración de la aplicación leída de variables de entorno (o `.env`).

Los secretos se guardan como `SecretStr` para que no aparezcan al imprimir
o registrar la configuración (RNF-01, RNF-05).
"""

from functools import lru_cache

from pydantic import BaseModel, Field, SecretStr, ValidationError, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic_settings.exceptions import SettingsError


class ErrorConfiguracion(RuntimeError):
    """La configuración está incompleta o es inválida."""


class Revendedor(BaseModel):
    """Revendedor del equipo que se publica en `/resellers` (RF-62)."""

    nombre: str = Field(min_length=1, max_length=60)
    # Solo dígitos con código de país (se usa en https://wa.me/<número>).
    whatsapp: str | None = Field(default=None, pattern=r"^[0-9]{8,15}$")
    # Usuario de Telegram sin «@» (se usa en https://t.me/<usuario>).
    telegram: str | None = Field(default=None, pattern=r"^[A-Za-z0-9_]{5,32}$")
    # Nombres de archivos WebP de app/static/inicio/ (foto y QR de Telegram).
    foto: str | None = Field(default=None, pattern=r"^[a-z0-9_-]+\.webp$")
    qr_telegram: str | None = Field(default=None, pattern=r"^[a-z0-9_-]+\.webp$")

    @model_validator(mode="after")
    def _al_menos_un_canal(self) -> "Revendedor":
        if not self.whatsapp and not self.telegram:
            raise ValueError("cada revendedor necesita whatsapp o telegram")
        return self


class Configuracion(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    ventasff_api_key: SecretStr = Field(min_length=1)
    database_url: SecretStr = Field(min_length=1)
    secret_key: SecretStr = Field(min_length=32)
    cookie_secure: bool
    # Opcional: en desarrollo puede apuntar al simulador (tests/fake_ventasff.py).
    ventasff_url: str = "https://ventasff.com/api/reseller"
    # Opcional (RNF-16): cabecera con la IP real del cliente tras un proxy, p. ej. CF-Connecting-IP.
    client_ip_header: str = ""
    # Opcional (RF-58): correo de contacto del pie y de las páginas legales; vacío lo oculta.
    contact_email: str = ""
    # Opcional (RF-62): JSON en una línea con la lista de revendedores de `/resellers`.
    resellers: list[Revendedor] = []
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
    except SettingsError as error:
        # Un JSON mal formado (p. ej. RESELLERS); el mensaje nombra el campo, no el valor.
        raise ErrorConfiguracion(
            f"Configuración inválida. Revisa el archivo .env (ver .env.example): {error}"
        ) from None


@lru_cache
def obtener_configuracion() -> Configuracion:
    return cargar_configuracion()
