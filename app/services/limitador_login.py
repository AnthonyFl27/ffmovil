"""Limitador de intentos fallidos de login en memoria (RF-05, plan sec. 7).

Cuenta los fallos de login por par (usuario, IP), por usuario (desde cualquier IP) y
por IP. Al llegar a su máximo dentro de la ventana deslizante, la clave queda
bloqueada durante `bloqueo` segundos. No usa base de datos ni red; el reloj es inyectable para las pruebas.
Es síncrono: corre en un único event loop, así que no necesita cerrojo.
"""

import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field

FALLOS_POR_USUARIO_IP = 5
FALLOS_POR_CUENTA = 10
FALLOS_POR_IP = 20
VENTANA_SEGUNDOS = 15 * 60
BLOQUEO_SEGUNDOS = 15 * 60


@dataclass
class _Registro:
    """Marcas de fallo de una clave y el instante en que vence su bloqueo, si lo hay."""

    marcas: deque[float] = field(default_factory=deque)
    hasta: float | None = None


# Un usuario válido tiene como mucho 30 caracteres (RF-07): lo que sobra no distingue
# cuentas y recortarlo evita guardar como clave un texto de 64 KB.
LARGO_CLAVE_USUARIO = 31


def _normalizar(usuario: str) -> str:
    """El usuario se compara sin espacios sobrantes, sin distinguir mayúsculas y recortado."""
    return usuario.strip().lower()[:LARGO_CLAVE_USUARIO]


class LimitadorLogin:
    """Bloquea nuevos intentos tras demasiados fallos por par (usuario, IP), usuario o IP."""

    def __init__(
        self,
        *,
        max_por_par: int = FALLOS_POR_USUARIO_IP,
        max_por_cuenta: int = FALLOS_POR_CUENTA,
        max_por_ip: int = FALLOS_POR_IP,
        ventana: float = VENTANA_SEGUNDOS,
        bloqueo: float = BLOQUEO_SEGUNDOS,
        reloj: Callable[[], float] = time.monotonic,
    ) -> None:
        if max_por_par < 1:
            raise ValueError("max_por_par debe ser >= 1")
        if max_por_cuenta < 1:
            raise ValueError("max_por_cuenta debe ser >= 1")
        if max_por_ip < 1:
            raise ValueError("max_por_ip debe ser >= 1")
        if ventana <= 0:
            raise ValueError("ventana debe ser > 0")
        if bloqueo <= 0:
            raise ValueError("bloqueo debe ser > 0")
        self._max_par = max_por_par
        self._max_cuenta = max_por_cuenta
        self._max_ip = max_por_ip
        self._ventana = ventana
        self._bloqueo = bloqueo
        self._reloj = reloj
        self._pares: dict[tuple[str, str], _Registro] = {}
        self._cuentas: dict[str, _Registro] = {}
        self._ips: dict[str, _Registro] = {}
        self._proximo_barrido: float | None = None

    def _actualizar(self, reg: _Registro, ahora: float) -> None:
        """Vacía un bloqueo vencido (con sus marcas) y poda las marcas fuera de la ventana."""
        if reg.hasta is not None and ahora >= reg.hasta:
            reg.hasta = None
            reg.marcas.clear()
        while reg.marcas and ahora - reg.marcas[0] >= self._ventana:
            reg.marcas.popleft()

    @staticmethod
    def _vacio(reg: _Registro) -> bool:
        return not reg.marcas and reg.hasta is None

    def _barrer(self, ahora: float) -> None:
        """Elimina las claves sin marcas ni bloqueo vigente; se ejecuta como mucho una vez por ventana."""
        if self._proximo_barrido is not None and ahora < self._proximo_barrido:
            return
        self._proximo_barrido = ahora + self._ventana
        for diccionario in (self._pares, self._cuentas, self._ips):
            for clave in list(diccionario):
                reg = diccionario[clave]
                self._actualizar(reg, ahora)
                if self._vacio(reg):
                    del diccionario[clave]

    def _bloqueada(self, diccionario: dict, clave: object, ahora: float) -> bool:
        reg = diccionario.get(clave)
        if reg is None:
            return False
        self._actualizar(reg, ahora)
        if self._vacio(reg):
            del diccionario[clave]
            return False
        return reg.hasta is not None

    def _sumar(self, diccionario: dict, clave: object, maximo: int, ahora: float) -> None:
        reg = diccionario.get(clave)
        if reg is None:
            reg = diccionario[clave] = _Registro()
        self._actualizar(reg, ahora)
        reg.marcas.append(ahora)
        if len(reg.marcas) >= maximo:
            reg.hasta = ahora + self._bloqueo

    def bloqueado(self, usuario: str, ip: str) -> bool:
        """True si el par (usuario, IP), el usuario o la IP tienen un bloqueo vigente."""
        ahora = self._reloj()
        self._barrer(ahora)
        nombre = _normalizar(usuario)
        bloqueo_par = self._bloqueada(self._pares, (nombre, ip), ahora)
        bloqueo_cuenta = self._bloqueada(self._cuentas, nombre, ahora)
        bloqueo_ip = self._bloqueada(self._ips, ip, ahora)
        return bloqueo_par or bloqueo_cuenta or bloqueo_ip

    def registrar_fallo(self, usuario: str, ip: str) -> None:
        """Cuenta un fallo de login para el par, el usuario y la IP."""
        ahora = self._reloj()
        self._barrer(ahora)
        nombre = _normalizar(usuario)
        self._sumar(self._pares, (nombre, ip), self._max_par, ahora)
        self._sumar(self._cuentas, nombre, self._max_cuenta, ahora)
        self._sumar(self._ips, ip, self._max_ip, ahora)

    def registrar_exito(self, usuario: str, ip: str) -> None:
        """Olvida los fallos y el bloqueo del par; el usuario y la IP no se tocan.

        Así un acierto del dueño no devuelve intentos a quien adivina desde otras IP.
        """
        self._pares.pop((_normalizar(usuario), ip), None)
