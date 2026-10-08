"""Infraestructura de las páginas web (plan sec. 6.1): plantillas, filtros y sesión.

Las páginas usan las dependencias de sesión de la API. Sin sesión redirigen a
`/entrar`; con `debe_cambiar_clave`, a `/clave` (RF-02); con el rol equivocado,
al inicio de su rol. A una petición HTMX la redirección se indica con `HX-Redirect`.
"""

from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Annotated

from fastapi import Depends, HTTPException, Request, Response, status
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from markupsafe import Markup

from app.routers.dependencias import Bd, SesionActual, usuario_en_sesion

DIRECTORIO_PLANTILLAS = Path(__file__).resolve().parent.parent / "templates"
DIRECTORIO_ESTATICOS = Path(__file__).resolve().parent.parent / "static"

INICIO_CLIENTE = "/inicio"
INICIO_ADMIN = "/gestion"
PAGINA_ENTRAR = "/entrar"
PAGINA_CLAVE = "/clave"


def usd(monto: Decimal | str | None) -> str:
    """Monto en USD con 2 decimales (RF-36)."""
    if monto is None:
        return "—"
    return f"{Decimal(monto):.2f} USD"


def fecha(valor: datetime | None) -> Markup:
    """Fecha UTC en `<time>`; `app.js` la muestra en la zona del navegador (RNF-09)."""
    if valor is None:
        return Markup("—")
    if valor.tzinfo is None:
        valor = valor.replace(tzinfo=UTC)
    valor = valor.astimezone(UTC)
    return Markup('<time datetime="{}" data-local>{}</time>').format(
        valor.isoformat(), valor.strftime("%Y-%m-%d %H:%M UTC")
    )


def texto(valor) -> str:
    """Valor opcional como texto; el autoescape de Jinja2 lo escapa."""
    return "—" if valor is None or valor == "" else str(valor)


plantillas = Jinja2Templates(directory=DIRECTORIO_PLANTILLAS)
plantillas.env.filters["usd"] = usd
plantillas.env.filters["fecha"] = fecha
plantillas.env.filters["texto"] = texto


def es_htmx(request: Request) -> bool:
    return request.headers.get("HX-Request") == "true"


def es_parcial(request: Request, destino: str) -> bool:
    """Petición HTMX que solo reemplaza `#destino` (no una restauración del historial)."""
    return (
        es_htmx(request)
        and request.headers.get("HX-History-Restore-Request") != "true"
        and request.headers.get("HX-Target") == destino
    )


def render(
    request: Request,
    plantilla: str,
    actual: SesionActual | None = None,
    *,
    status_code: int = status.HTTP_200_OK,
    **contexto,
) -> Response:
    if actual is not None:
        contexto.setdefault("usuario", actual.usuario.usuario)
        contexto.setdefault("rol", actual.usuario.rol)
        contexto.setdefault("csrf", actual.csrf)
    return plantillas.TemplateResponse(request, plantilla, contexto, status_code=status_code)


def error(request: Request, mensaje: str, status_code: int, destino: str | None = None) -> Response:
    """Fragmento con el mensaje de error; HTMX también muestra los 4xx (plan sec. 6.1).

    `destino` (`#id`) lo muestra en otro elemento que el del formulario (`HX-Retarget`).
    """
    respuesta = render(request, "parciales/error.html", mensaje=mensaje, status_code=status_code)
    if destino:
        respuesta.headers["HX-Retarget"] = destino
        respuesta.headers["HX-Reswap"] = "innerHTML"
    return respuesta


def redirigir(destino: str) -> Response:
    """Redirección tras un formulario HTMX (cabecera `HX-Redirect`)."""
    return Response(headers={"HX-Redirect": destino})


class Redirigir(Exception):  # señal de control, no un error
    def __init__(self, destino: str) -> None:
        super().__init__(destino)
        self.destino = destino


class ErrorWeb(Exception):
    def __init__(self, mensaje: str, status_code: int) -> None:
        super().__init__(mensaje)
        self.mensaje = mensaje
        self.status_code = status_code


async def manejar_redireccion(request: Request, exc: Redirigir) -> Response:
    if es_htmx(request):
        return redirigir(exc.destino)
    return RedirectResponse(exc.destino, status_code=status.HTTP_303_SEE_OTHER)


async def manejar_error_web(request: Request, exc: ErrorWeb) -> Response:
    plantilla = "parciales/error.html" if es_htmx(request) else "error.html"
    return render(request, plantilla, mensaje=exc.mensaje, status_code=exc.status_code)


def inicio_de(actual: SesionActual) -> str:
    if actual.usuario.debe_cambiar_clave:
        return PAGINA_CLAVE
    return INICIO_ADMIN if actual.usuario.rol == "admin" else INICIO_CLIENTE


async def sesion_opcional(request: Request, bd: Bd) -> SesionActual | None:
    try:
        return await usuario_en_sesion(request, bd)
    except HTTPException:
        return None


async def sesion_web(request: Request, bd: Bd) -> SesionActual:
    """Cualquier sesión válida (cambio de clave y salir)."""
    try:
        return await usuario_en_sesion(request, bd)
    except HTTPException as fallo:
        if fallo.status_code == status.HTTP_401_UNAUTHORIZED:
            raise Redirigir(PAGINA_ENTRAR) from None
        # CSRF ausente o inválido.
        raise ErrorWeb(fallo.detail, fallo.status_code) from None


SesionWeb = Annotated[SesionActual, Depends(sesion_web)]


async def cliente_web(actual: SesionWeb) -> SesionActual:
    if actual.usuario.debe_cambiar_clave or actual.usuario.rol != "cliente":
        raise Redirigir(inicio_de(actual))
    return actual


async def admin_web(actual: SesionWeb) -> SesionActual:
    if actual.usuario.debe_cambiar_clave or actual.usuario.rol != "admin":
        raise Redirigir(inicio_de(actual))
    return actual


ClienteWeb = Annotated[SesionActual, Depends(cliente_web)]
AdminWeb = Annotated[SesionActual, Depends(admin_web)]
