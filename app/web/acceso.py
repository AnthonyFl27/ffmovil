"""Páginas de acceso: entrar, cambiar contraseña y salir (RF-01, RF-02, RF-04 a RF-08)."""

from typing import Annotated

from fastapi import APIRouter, Depends, Form, HTTPException, Request, Response
from fastapi.responses import RedirectResponse

from app.routers import auth
from app.routers.dependencias import Bd, SesionActual
from app.schemas.auth import CambioClave, Login
from app.web.plantillas import (
    PAGINA_ENTRAR,
    SesionWeb,
    error,
    inicio_de,
    redirigir,
    render,
    sesion_opcional,
)

router = APIRouter(include_in_schema=False)

SesionOpcional = Annotated[SesionActual | None, Depends(sesion_opcional)]


@router.get("/")
async def raiz(actual: SesionOpcional):
    """Lleva al inicio del rol, a cambiar la clave o a entrar."""
    destino = inicio_de(actual) if actual is not None else PAGINA_ENTRAR
    return RedirectResponse(destino, status_code=303)


@router.get("/login")
async def entrar(request: Request, actual: SesionOpcional):
    if actual is not None:
        return RedirectResponse(inicio_de(actual), status_code=303)
    return render(request, "acceso/entrar.html")


@router.post("/login")
async def entrar_enviar(
    request: Request,
    bd: Bd,
    usuario: Annotated[str, Form()] = "",
    clave: Annotated[str, Form()] = "",
):
    respuesta = Response()
    try:
        info = await auth.login(Login(usuario=usuario, clave=clave), request, respuesta, bd)
    except HTTPException as fallo:
        return error(request, fallo.detail, fallo.status_code)
    respuesta.headers["HX-Redirect"] = "/clave" if info.debe_cambiar_clave else "/"
    return respuesta


@router.get("/clave")
async def clave(request: Request, actual: SesionWeb):
    return render(
        request, "acceso/clave.html", actual, obligatorio=actual.usuario.debe_cambiar_clave
    )


@router.post("/clave")
async def clave_enviar(
    request: Request,
    actual: SesionWeb,
    bd: Bd,
    clave_actual: Annotated[str, Form()] = "",
    clave_nueva: Annotated[str, Form()] = "",
):
    respuesta = Response()
    datos = CambioClave(clave_actual=clave_actual, clave_nueva=clave_nueva)
    try:
        await auth.cambiar_clave(datos, request, respuesta, actual, bd)
    except HTTPException as fallo:
        return error(request, fallo.detail, fallo.status_code)
    respuesta.headers["HX-Redirect"] = "/"
    return respuesta


@router.post("/salir")
async def salir(actual: SesionWeb, bd: Bd):
    respuesta = redirigir(PAGINA_ENTRAR)
    await auth.logout(respuesta, actual, bd)
    return respuesta
