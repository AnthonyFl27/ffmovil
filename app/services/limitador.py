"""Limitador de tasa en ventana deslizante para las llamadas a VentasFF (RN-07).

Guarda las marcas de tiempo de las últimas adquisiciones y no permite más de
`maximo` dentro de cualquier ventana de `ventana` segundos. No usa base de
datos ni red; el reloj y la espera son inyectables para las pruebas.
"""

import asyncio
import time
from collections import deque
from collections.abc import Awaitable, Callable

# Límites propios, por debajo de los topes del proveedor (RN-07: 60 peticiones/min
# y 10 recargas/min). Dejan margen para reintentos y llamadas de sincronización.
RECARGAS_POR_MINUTO = 8
PETICIONES_POR_MINUTO = 50


class LimitadorTasa:
    """Permite como máximo `maximo` adquisiciones por cada `ventana` segundos."""

    def __init__(
        self,
        maximo: int,
        ventana: float = 60.0,
        *,
        reloj: Callable[[], float] = time.monotonic,
        dormir: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        if maximo < 1:
            raise ValueError("maximo debe ser >= 1")
        if ventana <= 0:
            raise ValueError("ventana debe ser > 0")
        self._maximo = maximo
        self._ventana = ventana
        self._reloj = reloj
        self._dormir = dormir
        self._marcas: deque[float] = deque()
        self._cerrojo = asyncio.Lock()

    def _podar(self, ahora: float) -> None:
        """Descarta las marcas que ya salieron de la ventana."""
        while self._marcas and ahora - self._marcas[0] >= self._ventana:
            self._marcas.popleft()

    async def adquirir(self) -> float:
        """Espera hasta que haya cupo y registra la adquisición.

        Devuelve los segundos esperados (0.0 si no hubo que esperar). La espera
        se hace con el cerrojo tomado, así que las llamadas concurrentes salen
        en orden FIFO y nunca superan `maximo` dentro de una ventana.
        """
        esperado = 0.0
        async with self._cerrojo:
            while True:
                ahora = self._reloj()
                self._podar(ahora)
                if len(self._marcas) < self._maximo:
                    self._marcas.append(ahora)
                    return esperado
                # La marca más antigua sale de la ventana en este instante.
                espera = self._marcas[0] + self._ventana - ahora
                esperado += espera
                await self._dormir(espera)

    def disponibles(self) -> int:
        """Cuántas adquisiciones podrían hacerse ahora mismo sin esperar."""
        self._podar(self._reloj())
        return self._maximo - len(self._marcas)
