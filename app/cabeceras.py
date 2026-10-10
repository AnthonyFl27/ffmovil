"""Cabeceras de seguridad en todas las respuestas (RNF-14, plan sec. 7).

Middleware ASGI puro: añade las cabeceras al inicio de cada respuesta HTTP sin
leer ni copiar el cuerpo. `Cache-Control: no-store` se omite bajo `/static`, que
conserva su propio ETag.
"""

from starlette.types import ASGIApp, Message, Receive, Scope, Send

CSP = (
    "default-src 'self'; img-src 'self' data:; frame-ancestors 'none'; "
    "form-action 'self'; base-uri 'none'"
)

CABECERAS: tuple[tuple[bytes, bytes], ...] = (
    (b"x-content-type-options", b"nosniff"),
    (b"x-frame-options", b"DENY"),
    (b"referrer-policy", b"same-origin"),
    (b"content-security-policy", CSP.encode()),
)
NO_STORE = (b"cache-control", b"no-store")


class CabecerasSeguridad:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        estatico = scope["path"].startswith("/static/")

        async def send_con_cabeceras(mensaje: Message) -> None:
            if mensaje["type"] == "http.response.start":
                propias = {nombre for nombre, _ in CABECERAS}
                existentes = [
                    (n, v) for n, v in mensaje.get("headers", []) if n.lower() not in propias
                ]
                extra = list(CABECERAS)
                if not estatico:
                    existentes = [(n, v) for n, v in existentes if n.lower() != b"cache-control"]
                    extra.append(NO_STORE)
                mensaje = {**mensaje, "headers": existentes + extra}
            await send(mensaje)

        await self.app(scope, receive, send_con_cabeceras)
