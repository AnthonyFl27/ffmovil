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


# T-116 (RF-05, CHG-019): tope por cuenta. Diez fallos del mismo usuario desde cualquier
# IP bloquean la cuenta 15 min; un éxito no la desbloquea ni le devuelve intentos.


def test_fallos_desde_ips_distintas_bloquean_la_cuenta_al_decimo():
    """T-116 RF-05: 9 fallos desde 9 IPs no bloquean la cuenta; el 10.º la bloquea."""
    lim, _ = _limitador()
    for n in range(1, 10):
        lim.registrar_fallo("ana", f"203.0.113.{n}")
    assert lim.bloqueado("ana", "203.0.113.50") is False
    lim.registrar_fallo("ana", "203.0.113.10")
    assert lim.bloqueado("ana", "198.51.100.200") is True


def test_cuenta_bloqueada_no_afecta_a_otra_cuenta_desde_ip_limpia():
    """T-116 RF-05: con 'ana' bloqueada por cuenta, 'luis' desde una IP limpia entra."""
    lim, _ = _limitador()
    for n in range(1, 11):
        lim.registrar_fallo("ana", f"203.0.113.{n}")
    assert lim.bloqueado("ana", "198.51.100.1") is True
    assert lim.bloqueado("luis", "198.51.100.1") is False


def test_bloqueo_de_cuenta_vence_a_los_900_s_del_decimo_fallo():
    """T-116 RF-05: el bloqueo por cuenta dura 900 s desde el 10.º fallo, no el primero."""
    lim, reloj = _limitador()
    for n in range(1, 10):
        lim.registrar_fallo("ana", f"203.0.113.{n}")
    reloj.avanzar(100)
    lim.registrar_fallo("ana", "203.0.113.10")
    reloj.avanzar(899)
    assert lim.bloqueado("ana", "198.51.100.1") is True
    reloj.avanzar(1)
    assert lim.bloqueado("ana", "198.51.100.1") is False


def test_intentos_rechazados_no_alargan_el_bloqueo_de_cuenta():
    """T-116 RF-05: consultar durante el bloqueo no lo extiende; vence 900 s después del fallo 10."""
    lim, reloj = _limitador()
    for n in range(1, 11):
        lim.registrar_fallo("ana", f"203.0.113.{n}")
    reloj.avanzar(600)
    for _ in range(3):
        assert lim.bloqueado("ana", "198.51.100.1") is True
    reloj.avanzar(300)
    assert lim.bloqueado("ana", "198.51.100.1") is False


def test_exito_limpia_el_par_pero_no_la_cuenta_ni_devuelve_intentos():
    """T-116 RF-05: 9 fallos + éxito de 'ana' + 1 fallo más desde otra IP bloquean la cuenta."""
    lim, _ = _limitador()
    for n in range(1, 10):
        lim.registrar_fallo("ana", f"203.0.113.{n}")
    lim.registrar_exito("ana", "203.0.113.1")
    lim.registrar_fallo("ana", "203.0.113.99")
    assert lim.bloqueado("ana", "198.51.100.1") is True


def test_exito_deja_el_par_limpio_con_la_cuenta_bajo_el_tope():
    """T-116 RF-05: tras un éxito, 4 fallos más del par no bloquean (cuenta: 8 < 10)."""
    lim, _ = _limitador()
    for _ in range(4):
        lim.registrar_fallo("ana", IP)
    lim.registrar_exito("ana", IP)
    for _ in range(4):
        lim.registrar_fallo("ana", IP)
    assert lim.bloqueado("ana", IP) is False
    assert lim.bloqueado("ana", "198.51.100.1") is False


def test_mayusculas_y_espacios_suman_la_misma_cuenta():
    """T-116 RF-05: 'Ana', ' ana ' y 'ANA' desde IPs distintas cuentan como una cuenta."""
    lim, _ = _limitador(max_por_cuenta=3)
    lim.registrar_fallo("Ana", "203.0.113.1")
    lim.registrar_fallo(" ana ", "203.0.113.2")
    assert lim.bloqueado("ana", "198.51.100.1") is False
    lim.registrar_fallo("ANA", "203.0.113.3")
    assert lim.bloqueado("ana", "198.51.100.1") is True


def test_nombre_de_64_kb_se_guarda_recortado_a_31_caracteres():
    """T-116 RF-05: un usuario de 64 KB no se guarda entero como clave del limitador."""
    lim, _ = _limitador()
    lim.registrar_fallo("a" * 65536, IP)
    assert "a" * 31 in lim._cuentas
    assert all(len(clave) <= 31 for clave in lim._cuentas)
    assert all(len(usuario) <= 31 for usuario, _ in lim._pares)


def test_cinco_fallos_de_un_par_bloquean_solo_ese_par():
    """T-116 RF-05: el tope por par (5 fallos) sigue igual y no bloquea otra IP."""
    lim, _ = _limitador()
    for _ in range(5):
        lim.registrar_fallo("ana", IP)
    assert lim.bloqueado("ana", IP) is True
    assert lim.bloqueado("ana", "198.51.100.1") is False


def test_veinte_fallos_de_usuarios_distintos_bloquean_solo_la_ip():
    """T-116 RF-05: el tope por IP (20 fallos) sigue igual y no bloquea la cuenta en otra IP."""
    lim, _ = _limitador()
    for i in range(20):
        lim.registrar_fallo(f"usuario{i}", IP)
    assert lim.bloqueado("nuevo", IP) is True
    assert lim.bloqueado("nuevo", "198.51.100.1") is False


def test_max_por_cuenta_cero_lanza_value_error():
    """T-116 RF-05: el tope por cuenta debe ser al menos 1."""
    with pytest.raises(ValueError):
        LimitadorLogin(max_por_cuenta=0)
