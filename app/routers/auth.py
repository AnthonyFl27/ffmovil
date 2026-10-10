"""Login, logout, sesión actual y cambio de contraseña (RF-01, RF-02, RF-04 a RF-08)."""

from fastapi import APIRouter, HTTPException, Request, Response, status
from sqlalchemy import func

from app.models import Usuario
from app.routers.dependencias import (
    COOKIE_SESION,
    Bd,
    EnSesion,
    ip_cliente,
)
from app.schemas.auth import CambioClave, InfoSesion, Login
from app.services import auth_service, sesiones
from app.services.auth_service import (
    LARGO_MAXIMO_CLAVE,
    LARGO_MAXIMO_USUARIO,
    ClaveInvalida,
    UsuarioBloqueado,
)

router = APIRouter(prefix="/auth", tags=["auth"])

MENSAJE_CREDENCIALES = "Usuario o contraseña incorrectos."
MENSAJE_DEMASIADOS_INTENTOS = "Demasiados intentos fallidos. Intenta de nuevo en 15 minutos."
MENSAJE_CLAVE_ACTUAL = "La contraseña actual es incorrecta."


def info_sesion(usuario: Usuario, csrf: str) -> InfoSesion:
    return InfoSesion(
        usuario=usuario.usuario,
        rol=usuario.rol,
        debe_cambiar_clave=usuario.debe_cambiar_clave,
        csrf=csrf,
    )


def poner_cookie(request: Request, response: Response, token: str) -> None:
    response.set_cookie(
        COOKIE_SESION,
        token,
        httponly=True,
        samesite="lax",
        secure=request.app.state.cookie_secure,
        path="/",
    )


@router.post("/login", response_model=InfoSesion)
async def login(datos: Login, request: Request, response: Response, bd: Bd):
    limitador = request.app.state.limitador_login
    ip = ip_cliente(request) or "desconocida"
    # RF-05: con el tope superado no se verifica la clave.
    if limitador.bloqueado(datos.usuario, ip):
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, MENSAJE_DEMASIADOS_INTENTOS)
    # RNF-13: datos que no pueden ser válidos no llegan a la BD ni al hash.
    if len(datos.usuario.strip()) > LARGO_MAXIMO_USUARIO or len(datos.clave) > LARGO_MAXIMO_CLAVE:
        limitador.registrar_fallo(datos.usuario, ip)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, MENSAJE_CREDENCIALES)
    try:
        usuario = await auth_service.autenticar(bd, datos.usuario, datos.clave)
    except UsuarioBloqueado as error:
        raise HTTPException(status.HTTP_403_FORBIDDEN, str(error)) from None
    if usuario is None:
        limitador.registrar_fallo(datos.usuario, ip)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, MENSAJE_CREDENCIALES)
    limitador.registrar_exito(datos.usuario, ip)

    usuario.ultimo_login = func.now()
    await sesiones.limpiar_vencidas(bd)
    creada = await sesiones.crear_sesion(bd, usuario.id, ip_cliente(request))
    await bd.commit()
    await bd.refresh(usuario)
    poner_cookie(request, response, creada.token)
    return info_sesion(usuario, creada.csrf)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(response: Response, actual: EnSesion, bd: Bd):
    await sesiones.cerrar_sesion(bd, actual.token_hash)
    await bd.commit()
    response.delete_cookie(COOKIE_SESION, path="/")


@router.get("/sesion", response_model=InfoSesion)
async def sesion_actual(actual: EnSesion):
    return info_sesion(actual.usuario, actual.csrf)


@router.post("/cambiar-clave", response_model=InfoSesion)
async def cambiar_clave(
    datos: CambioClave, request: Request, response: Response, actual: EnSesion, bd: Bd
):
    """Cambio de contraseña, obligatorio en el primer acceso (RF-02, RF-08).

    Cierra todas las sesiones del usuario y abre una nueva para quien la cambió (RF-06).
    """
    usuario = actual.usuario
    if not auth_service.verificar_clave(usuario.hash_password, datos.clave_actual):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, MENSAJE_CLAVE_ACTUAL)
    try:
        auth_service.validar_clave_nueva(datos.clave_nueva, usuario.hash_password)
    except ClaveInvalida as error:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(error)) from None

    usuario.hash_password = auth_service.hashear_clave(datos.clave_nueva)
    usuario.debe_cambiar_clave = False
    await sesiones.cerrar_sesiones_de(bd, usuario.id)
    creada = await sesiones.crear_sesion(bd, usuario.id, ip_cliente(request))
    await bd.commit()
    poner_cookie(request, response, creada.token)
    return info_sesion(usuario, creada.csrf)
