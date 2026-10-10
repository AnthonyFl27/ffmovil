import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.cabeceras import CabecerasSeguridad
from app.config import obtener_configuracion
from app.db import ErrorConexionBD, crear_fabrica_sesiones, crear_motor, verificar_conexion
from app.limite_cuerpo import LimiteCuerpo
from app.logs import configurar_logs
from app.routers import admin, auth, me, paquetes, recargas
from app.services.limitador import (
    PEDIDOS_POR_MINUTO,
    PETICIONES_ANONIMAS_POR_MINUTO,
    PETICIONES_POR_MINUTO,
    PETICIONES_USUARIO_POR_MINUTO,
    RECARGAS_POR_MINUTO,
    VALIDACIONES_POR_MINUTO,
    LimitadorPorUsuario,
    LimitadorTasa,
)
from app.services.limitador_login import LimitadorLogin
from app.services.recuperacion import recuperar_pedidos_huerfanos
from app.services.tareas import crear_programador
from app.services.ventasff_client import ClienteVentasFF
from app.web import montar as montar_web

logger = logging.getLogger(__name__)

TIMEOUT_CIERRE_SEGUNDOS = 100


@asynccontextmanager
async def lifespan(app: FastAPI):
    config = obtener_configuracion()
    configurar_logs(config)
    motor = crear_motor(config.database_url.get_secret_value())
    try:
        await verificar_conexion(motor)
    except Exception:
        await motor.dispose()
        raise
    app.state.motor = motor
    app.state.sesiones = crear_fabrica_sesiones(motor)
    app.state.cookie_secure = config.cookie_secure
    app.state.limitador_login = LimitadorLogin()
    app.state.limitador_validaciones = LimitadorPorUsuario(VALIDACIONES_POR_MINUTO)
    app.state.limitador_pedidos = LimitadorPorUsuario(PEDIDOS_POR_MINUTO)
    app.state.limitador_peticiones = LimitadorPorUsuario(PETICIONES_USUARIO_POR_MINUTO)
    app.state.limitador_anonimo = LimitadorPorUsuario(PETICIONES_ANONIMAS_POR_MINUTO)
    app.state.cabecera_ip = config.client_ip_header
    # RN-09: pedidos que quedaron en PROCESANDO por un reinicio pasan a revisión.
    async with app.state.sesiones() as sesion:
        await recuperar_pedidos_huerfanos(sesion)

    def crear_cliente() -> ClienteVentasFF:
        return ClienteVentasFF(config.ventasff_api_key.get_secret_value(), config.ventasff_url)

    # Un solo cliente VentasFF para las rutas: comparte el límite general de peticiones
    # y la pausa por RATE_LIMITED (RN-07). Las recargas tienen además su propio límite.
    app.state.ventasff = ClienteVentasFF(
        config.ventasff_api_key.get_secret_value(),
        config.ventasff_url,
        limitador=LimitadorTasa(PETICIONES_POR_MINUTO),
    )
    app.state.limitador_recargas = LimitadorTasa(RECARGAS_POR_MINUTO)
    # Para "sincronizar ahora" desde el panel (cada sincronización abre y cierra su cliente).
    app.state.crear_cliente_ventasff = crear_cliente
    app.state.tareas_recarga = set()

    # Sincronización diaria del catálogo (RF-10); la app corre con un solo worker.
    programador = crear_programador(app.state.sesiones, crear_cliente)
    programador.start()
    yield
    programador.shutdown(wait=False)
    # Deja terminar las recargas en curso; las que no terminen pasan a revisión al
    # volver a arrancar (RN-09).
    if app.state.tareas_recarga:
        await asyncio.wait(app.state.tareas_recarga, timeout=TIMEOUT_CIERRE_SEGUNDOS)
    await app.state.ventasff.cerrar()
    await motor.dispose()


# Sin documentación interactiva ni esquema públicos (RNF-15).
app = FastAPI(title="ffmovil", lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
# El último que se añade es el más externo: las cabeceras también cubren los 413 (RNF-14).
app.add_middleware(LimiteCuerpo)
app.add_middleware(CabecerasSeguridad)
app.include_router(auth.router)
app.include_router(me.router)
app.include_router(paquetes.router)
app.include_router(recargas.router)
app.include_router(admin.router)
montar_web(app)


@app.get("/health")
async def health(request: Request):
    try:
        await verificar_conexion(request.app.state.motor)
    except ErrorConexionBD as error:
        # El motivo va al log del servidor (sin contraseña), no a la respuesta.
        logger.warning("health: %s", error)
        return JSONResponse({"estado": "error", "bd": "error"}, status_code=503)
    return {"estado": "ok", "bd": "ok"}
