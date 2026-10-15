"""Página pública, páginas legales y contacto de revendedores (RF-58, RF-59, RF-62; plan sec. 6.3).

No leen paquetes, saldos ni pedidos y no llaman a VentasFF. Pasan por
`sesion_opcional`, que aplica el tope por IP a quien no tiene sesión (RNF-17).
"""

from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status

from app.config import ErrorConfiguracion, Revendedor
from app.routers.dependencias import SesionActual
from app.web.plantillas import DIRECTORIO_ESTATICOS, render, sesion_opcional

router = APIRouter(include_in_schema=False)

SesionOpcional = Annotated[SesionActual | None, Depends(sesion_opcional)]


def verificar_archivos_revendedores(revendedores: list[Revendedor]) -> None:
    """Falla al arrancar si la foto o el QR de un revendedor no existen en `static/inicio/`."""
    for revendedor in revendedores:
        for archivo in (revendedor.foto, revendedor.qr_telegram):
            if archivo and not (DIRECTORIO_ESTATICOS / "inicio" / archivo).is_file():
                raise ErrorConfiguracion(
                    f"RESELLERS: no existe app/static/inicio/{archivo} (revendedor «{revendedor.nombre}»)"
                )


def render_publica(request: Request, plantilla: str) -> Response:
    """Plantilla pública con el año actual y el correo de contacto (vacío lo oculta)."""
    return render(
        request,
        plantilla,
        anio=datetime.now(UTC).year,
        correo=getattr(request.app.state, "correo_contacto", ""),
        revendedores=getattr(request.app.state, "revendedores", []),
    )


@router.get("/terminos")
async def terminos(request: Request, _actual: SesionOpcional):
    return render_publica(request, "publica/terminos.html")


@router.get("/privacidad")
async def privacidad(request: Request, _actual: SesionOpcional):
    return render_publica(request, "publica/privacidad.html")


@router.get("/resellers")
async def revendedores(request: Request, _actual: SesionOpcional):
    """Contacto de los revendedores del equipo; sin ninguno definido no existe (RF-62)."""
    if not getattr(request.app.state, "revendedores", []):
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    return render_publica(request, "publica/resellers.html")
