"""Pruebas del limitador de intentos fallidos de login (RF-05). Sin BD ni red."""

import pytest

from app.services.limitador_login import LimitadorLogin

IP = "203.0.113.7"


class RelojFalso:
    def __init__(self, inicio: float = 1000.0) -> None:
        self.t = inicio

    def __call__(self) -> float:
        return self.t

    def avanzar(self, segundos: float) -> None:
        self.t += segundos


def _limitador(**kwargs) -> tuple[LimitadorLogin, RelojFalso]:
    reloj = RelojFalso()
    return LimitadorLogin(reloj=reloj, **kwargs), reloj


def test_par_bloquea_al_quinto_fallo_y_no_antes():
    lim, _ = _limitador()
    for _ in range(4):
        lim.registrar_fallo("ana", IP)
    assert lim.bloqueado("ana", IP) is False
    lim.registrar_fallo("ana", IP)
    assert lim.bloqueado("ana", IP) is True


def test_otro_usuario_desde_la_misma_ip_no_queda_bloqueado_por_el_par():
    lim, _ = _limitador()
    for _ in range(5):
        lim.registrar_fallo("ana", IP)
    assert lim.bloqueado("ana", IP) is True
    assert lim.bloqueado("luis", IP) is False


def test_veinte_fallos_desde_una_ip_bloquean_la_ip_para_cualquier_usuario():
    lim, _ = _limitador()
    for i in range(19):
        lim.registrar_fallo(f"usuario{i}", IP)
    assert lim.bloqueado("nuevo", IP) is False
    lim.registrar_fallo("usuario19", IP)
    assert lim.bloqueado("nuevo", IP) is True
    assert lim.bloqueado("usuario0", IP) is True


def test_bloqueo_vence_a_los_900_segundos_y_el_contador_reinicia():
    lim, reloj = _limitador()
    for _ in range(5):
        lim.registrar_fallo("ana", IP)
    reloj.avanzar(899)
    assert lim.bloqueado("ana", IP) is True
    reloj.avanzar(1)
    assert lim.bloqueado("ana", IP) is False
    for _ in range(4):
        lim.registrar_fallo("ana", IP)
    assert lim.bloqueado("ana", IP) is False
    lim.registrar_fallo("ana", IP)
    assert lim.bloqueado("ana", IP) is True


def test_fallos_fuera_de_la_ventana_no_cuentan():
    lim, reloj = _limitador()
    for _ in range(4):
        lim.registrar_fallo("ana", IP)
    reloj.avanzar(900)
    lim.registrar_fallo("ana", IP)
    assert lim.bloqueado("ana", IP) is False


def test_exito_limpia_el_par_pero_no_la_ip():
    lim, _ = _limitador()
    for _ in range(4):
        lim.registrar_fallo("ana", IP)
    lim.registrar_exito("ana", IP)
    for _ in range(4):
        lim.registrar_fallo("ana", IP)
    assert lim.bloqueado("ana", IP) is False


def test_exito_no_levanta_el_bloqueo_de_la_ip():
    lim, _ = _limitador()
    for i in range(20):
        lim.registrar_fallo(f"usuario{i}", IP)
    lim.registrar_exito("usuario0", IP)
    assert lim.bloqueado("usuario0", IP) is True


def test_usuario_se_normaliza_con_mayusculas_y_espacios():
    lim, _ = _limitador()
    for _ in range(4):
        lim.registrar_fallo("  Ana ", IP)
    lim.registrar_fallo("ANA", IP)
    assert lim.bloqueado("ana", IP) is True
    assert lim.bloqueado(" aNa\t", IP) is True


def test_claves_sin_marcas_se_eliminan_al_podar():
    lim, reloj = _limitador()
    lim.registrar_fallo("ana", IP)
    reloj.avanzar(900)
    lim.bloqueado("otro", "198.51.100.1")
    assert lim.bloqueado("ana", IP) is False
    assert lim._pares == {}
    assert lim._ips == {}


def test_parametros_invalidos_lanzan_value_error():
    with pytest.raises(ValueError):
        LimitadorLogin(max_por_par=0)
    with pytest.raises(ValueError):
        LimitadorLogin(max_por_ip=0)
    with pytest.raises(ValueError):
        LimitadorLogin(ventana=0)
    with pytest.raises(ValueError):
        LimitadorLogin(ventana=-1)
    with pytest.raises(ValueError):
        LimitadorLogin(bloqueo=0)
