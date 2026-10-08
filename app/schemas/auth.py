"""Esquemas de autenticación (RF-01, RF-02)."""

from pydantic import BaseModel


class Login(BaseModel):
    usuario: str
    clave: str


class InfoSesion(BaseModel):
    usuario: str
    rol: str
    debe_cambiar_clave: bool
    # Token CSRF de la sesión: va en la cabecera X-CSRF-Token (plan sec. 7).
    csrf: str


class CambioClave(BaseModel):
    clave_actual: str
    clave_nueva: str
