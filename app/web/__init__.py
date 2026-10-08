"""Páginas web con Jinja2 + HTMX (Q-05, CHG-008; plan sec. 6.1)."""

from fastapi import APIRouter, FastAPI
from fastapi.staticfiles import StaticFiles

from app.web import acceso, admin, cliente
from app.web.plantillas import (
    DIRECTORIO_ESTATICOS,
    ErrorWeb,
    Redirigir,
    manejar_error_web,
    manejar_redireccion,
)

router = APIRouter(include_in_schema=False)
router.include_router(acceso.router)
router.include_router(cliente.router)
router.include_router(admin.router)


def montar(app: FastAPI) -> None:
    app.include_router(router)
    app.mount("/static", StaticFiles(directory=DIRECTORIO_ESTATICOS), name="static")
    app.add_exception_handler(Redirigir, manejar_redireccion)
    app.add_exception_handler(ErrorWeb, manejar_error_web)
