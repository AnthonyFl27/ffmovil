"""Página pública de presentación y páginas legales (RF-58, RF-59; plan sec. 6.3).

No leen paquetes, saldos ni pedidos y no llaman a VentasFF. Pasan por
`sesion_opcional`, que aplica el tope por IP a quien no tiene sesión (RNF-17).
"""

from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response

from app.routers.dependencias import SesionActual
from app.web.plantillas import render, sesion_opcional

router = APIRouter(include_in_schema=False)

SesionOpcional = Annotated[SesionActual | None, Depends(sesion_opcional)]


def render_publica(request: Request, plantilla: str) -> Response:
    """Plantilla pública con el año actual y el correo de contacto (vacío lo oculta)."""
    return render(
        request,
        plantilla,
        anio=datetime.now(UTC).year,
        correo=getattr(request.app.state, "correo_contacto", ""),
    )


@router.get("/terminos")
async def terminos(request: Request, _actual: SesionOpcional):
    return render_publica(request, "publica/terminos.html")


@router.get("/privacidad")
async def privacidad(request: Request, _actual: SesionOpcional):
    return render_publica(request, "publica/privacidad.html")
