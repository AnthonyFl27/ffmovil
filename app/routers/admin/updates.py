"""Novedades de la plataforma para el equipo admin (RF-63)."""

from fastapi import APIRouter, Request

from app.schemas.admin import ListaUpdates

router = APIRouter()


@router.get("/updates", response_model=ListaUpdates)
async def listar(request: Request):
    """Novedades de `app/updates.json`, la más reciente primero."""
    return ListaUpdates(updates=request.app.state.updates)
