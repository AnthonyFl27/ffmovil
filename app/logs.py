"""Registro de logs que enmascara secretos antes de escribirlos (RNF-05).

Ningún mensaje, argumento, traceback ni `repr` debe contener la API Key de
VentasFF, la `SECRET_KEY`, contraseñas de base de datos ni tokens `Bearer`.
El enmascarado se hace sobre el texto final que produce el formateador, así
que cubre mensajes, argumentos %, f-strings y excepciones.
"""

import logging
import re
from collections.abc import Iterable
from urllib.parse import quote

from sqlalchemy import make_url

from app.config import Configuracion

MASCARA = "***"

FORMATO_LOG = "%(asctime)s %(levelname)s [%(name)s] %(message)s"

# Atributo que marca los manejadores instalados por `configurar_logs`.
_MARCA = "_ffmovil_registro_seguro"

_LOGGERS_UVICORN = ("uvicorn", "uvicorn.error", "uvicorn.access")

_PATRON_BEARER = re.compile(r"\bbearer\s+[^\s'\"]+", re.IGNORECASE)


def enmascarar(texto: str, secretos: Iterable[str]) -> str:
    """Sustituye cada secreto no vacío y cualquier `Bearer <token>` por `***`.

    Los secretos más largos se sustituyen primero, para que un secreto que
    contiene a otro más corto quede enmascarado completo.
    """
    validos = sorted({s for s in secretos if s}, key=len, reverse=True)
    for secreto in validos:
        texto = texto.replace(secreto, MASCARA)
    return _PATRON_BEARER.sub(f"Bearer {MASCARA}", texto)


class FormateadorSeguro(logging.Formatter):
    """Formateador que enmascara los secretos del texto final de cada registro."""

    def __init__(
        self,
        secretos: Iterable[str] = (),
        fmt: str | None = None,
        datefmt: str | None = None,
        style: str = "%",
        validate: bool = True,
        *,
        defaults: dict | None = None,
    ) -> None:
        super().__init__(fmt, datefmt, style, validate, defaults=defaults)
        self._secretos = tuple(s for s in secretos if s)

    def format(self, record: logging.LogRecord) -> str:
        texto = super().format(record)
        # El traceback queda cacheado en el registro y otros manejadores lo
        # reutilizan; se enmascara también ahí para que no se filtre.
        if record.exc_text:
            record.exc_text = enmascarar(record.exc_text, self._secretos)
        return enmascarar(texto, self._secretos)


def secretos_de_configuracion(config: Configuracion) -> list[str]:
    """Devuelve los valores en claro de los secretos de la configuración."""
    secretos = [
        config.ventasff_api_key.get_secret_value(),
        config.secret_key.get_secret_value(),
    ]
    urls = [config.database_url.get_secret_value()]
    if config.test_database_url is not None:
        urls.append(config.test_database_url.get_secret_value())
    for url in urls:
        clave_bd = make_url(url).password
        if clave_bd:
            # También como aparece dentro de la URL (codificada).
            secretos += [clave_bd, quote(clave_bd, safe="")]
    return [s for s in secretos if s]


def configurar_logs(config: Configuracion, nivel: int = logging.INFO) -> None:
    """Instala un manejador seguro en el logger raíz (idempotente).

    También aplica el mismo formateador a los manejadores de uvicorn.
    """
    formateador = FormateadorSeguro(secretos_de_configuracion(config), FORMATO_LOG)

    raiz = logging.getLogger()
    for manejador in list(raiz.handlers):
        if getattr(manejador, _MARCA, False):
            raiz.removeHandler(manejador)

    manejador = logging.StreamHandler()
    setattr(manejador, _MARCA, True)
    manejador.setFormatter(formateador)
    raiz.addHandler(manejador)
    raiz.setLevel(nivel)

    for nombre in _LOGGERS_UVICORN:
        for existente in logging.getLogger(nombre).handlers:
            existente.setFormatter(formateador)
