"""Rutas `/admin/*`: todas exigen sesión de admin (RNF-03, T-061)."""

from fastapi import APIRouter, Depends

from app.routers.admin import usuarios
from app.routers.dependencias import require_admin

router = APIRouter(prefix="/admin", tags=["admin"], dependencies=[Depends(require_admin)])
router.include_router(usuarios.router)
