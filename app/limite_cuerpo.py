"""Límite de tamaño del cuerpo de las peticiones (RNF-13, plan sec. 7).

Middleware ASGI puro: rechaza con 413 antes de que FastAPI lea el cuerpo cuando
`Content-Length` ya lo supera, y corta el flujo si llega más de lo permitido sin
esa cabecera (transferencia por trozos o cabecera falsa).
"""

import json

from starlette.types import ASGIApp, Message, Receive, Scope, Send

LIMITE_CUERPO_BYTES = 64 * 1024
MENSAJE_CUERPO_GRANDE = "La petición es demasiado grande."


class CuerpoDemasiadoGrande(Exception):
    """El flujo recibido superó el límite."""


class LimiteCuerpo:
    def __init__(self, app: ASGIApp, maximo: int = LIMITE_CUERPO_BYTES) -> None:
        self.app = app
        self.maximo = maximo

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        declarado = dict(scope["headers"]).get(b"content-length", b"")
        if declarado.isdigit() and int(declarado) > self.maximo:
            await self._rechazar(send)
            return

        recibido = 0
        excedido = False
        respondio = False

        async def receive_limitado() -> Message:
            nonlocal recibido, excedido
            mensaje = await receive()
            if mensaje["type"] == "http.request":
                recibido += len(mensaje.get("body", b""))
                if recibido > self.maximo:
                    excedido = True
                    raise CuerpoDemasiadoGrande
            return mensaje

        async def send_vigilado(mensaje: Message) -> None:
            # FastAPI convierte cualquier error al leer el cuerpo en un 400: con el
            # límite superado, la respuesta de la app se sustituye por el 413.
            nonlocal respondio
            if excedido:
                if not respondio:
                    respondio = True
                    await self._rechazar(send)
                return
            if mensaje["type"] == "http.response.start":
                respondio = True
            await send(mensaje)

        try:
            await self.app(scope, receive_limitado, send_vigilado)
        except CuerpoDemasiadoGrande:
            if not respondio:
                await self._rechazar(send)

    @staticmethod
    async def _rechazar(send: Send) -> None:
        cuerpo = json.dumps({"detail": MENSAJE_CUERPO_GRANDE}).encode()
        await send(
            {
                "type": "http.response.start",
                "status": 413,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"content-length", str(len(cuerpo)).encode()),
                    (b"connection", b"close"),
                ],
            }
        )
        await send({"type": "http.response.body", "body": cuerpo})
