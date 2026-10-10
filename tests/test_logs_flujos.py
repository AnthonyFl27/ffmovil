"""T-081: los logs de la app no contienen la API Key ni contraseñas (RNF-05, RNF-01).

`test_logs.py` prueba el enmascarador. Aquí se comprueba además que el código no
escribe secretos en primer lugar: se recorren los flujos reales (login, cambio y
reseteo de clave, recargas con errores del proveedor) con un manejador SIN
enmascarar y se busca cada secreto en el texto emitido, con el nivel de producción.
"""

import io
import logging
import uuid

import pytest

from app.logs import FORMATO_LOG
from tests.test_integracion_escenarios import abonar, entorno, recargar  # noqa: F401
from tests.utilidades_api import CLAVE, crear_usuario_con_clave, iniciar_sesion

CLAVE_ERRONEA = "clave-equivocada-77"
CLAVE_NUEVA = "clave-nueva-segura-88"
CLAVE_ADMIN = "clave-del-admin-99"
CLAVE_CORTA = "corta1"


@pytest.fixture
def emitido():
    """Texto de todos los logs, tal como salen del código (sin enmascarar), nivel INFO."""
    flujo = io.StringIO()
    manejador = logging.StreamHandler(flujo)
    manejador.setFormatter(logging.Formatter(FORMATO_LOG))
    raiz = logging.getLogger()
    nivel = raiz.level
    raiz.addHandler(manejador)
    raiz.setLevel(logging.INFO)
    try:
        yield flujo
    finally:
        raiz.removeHandler(manejador)
        raiz.setLevel(nivel)


def sin_secretos(emitido: io.StringIO, secretos: list[str]) -> None:
    texto = emitido.getvalue()
    assert texto, "la prueba no generó ningún log: no comprueba nada"
    for secreto in secretos:
        assert secreto not in texto, f"el log contiene un secreto ({secreto[:6]}…)"
    # Ni hashes de contraseña ni cabeceras de autorización.
    assert "$argon2" not in texto
    assert "authorization" not in texto.lower()


async def test_acceso_y_claves_no_llegan_a_los_logs(api, sesion_bd, emitido):
    """Login (bueno, malo y bloqueado), cambio de clave y reseteo por el admin."""
    secretos = [CLAVE_ERRONEA, CLAVE_NUEVA, CLAVE_ADMIN, CLAVE_CORTA, CLAVE]
    cliente = await crear_usuario_con_clave(sesion_bd, "cliente")
    admin = await crear_usuario_con_clave(sesion_bd, "admin", clave=CLAVE_ADMIN)

    # Login incorrecto repetido hasta el bloqueo (RF-05) y luego uno válido de otra IP.
    http = api("10.0.0.7")
    for _ in range(6):
        await iniciar_sesion(http, cliente.usuario, CLAVE_ERRONEA)
    bloqueado = await iniciar_sesion(http, cliente.usuario, CLAVE)
    assert bloqueado.status_code == 429

    http = api("10.0.0.8")
    r = await iniciar_sesion(http, cliente.usuario, CLAVE)
    assert r.status_code == 200
    secretos += [r.json()["csrf"], http.cookies["sesion"]]

    # Cambio de clave: incorrecta, demasiado corta y correcta.
    cambio = {"clave_actual": CLAVE_ERRONEA, "clave_nueva": CLAVE_NUEVA}
    assert (await http.post("/auth/cambiar-clave", json=cambio)).status_code == 400
    cambio = {"clave_actual": CLAVE, "clave_nueva": CLAVE_CORTA}
    assert (await http.post("/auth/cambiar-clave", json=cambio)).status_code == 400
    cambio = {"clave_actual": CLAVE, "clave_nueva": CLAVE_NUEVA}
    assert (await http.post("/auth/cambiar-clave", json=cambio)).status_code == 200

    # El admin crea un cliente y resetea su clave; las claves temporales no se registran.
    http_admin = api()
    r = await iniciar_sesion(http_admin, admin.usuario, CLAVE_ADMIN)
    assert r.status_code == 200
    nuevo = await http_admin.post("/admin/usuarios", json={"usuario": f"n_{uuid.uuid4().hex[:8]}"})
    assert nuevo.status_code == 201, nuevo.text
    secretos.append(nuevo.json()["clave_temporal"])
    reseteo = await http_admin.post(f"/admin/usuarios/{cliente.id}/reset-clave")
    assert reseteo.status_code == 200, reseteo.text
    secretos.append(reseteo.json()["clave_temporal"])

    # Las mismas operaciones por las páginas web (formularios).
    web = api("10.0.0.9")
    resp = await web.post(
        "/login",
        data={"usuario": cliente.usuario, "clave": CLAVE_ERRONEA},
        headers={"HX-Request": "true"},
    )
    assert resp.status_code == 401

    sin_secretos(emitido, secretos)


@pytest.mark.parametrize(
    "escenario",
    ["ok", "INVALID_KEY", "INSUFFICIENT_CREDIT", "error_conexion", "timeout", "ilegible"],
)
async def test_recargas_no_registran_la_api_key(entorno, emitido, escenario):  # noqa: F811
    """Todos los desenlaces del proveedor (éxito, errores de cuenta, red, incierto)."""
    await abonar(entorno)
    pedido = await recargar(entorno, escenario)
    assert pedido["codigo"]
    # Además de la validación del jugador y la consulta de saldo del panel.
    r = await entorno.cliente.post(
        "/recargas/validar",
        json={"player_id": "75807448", "paquete_id": entorno.paquete_id},
    )
    assert r.status_code == 200
    assert (await entorno.admin.get("/admin/panel")).status_code == 200

    sin_secretos(emitido, [entorno.sim.api_key, entorno.cliente.cookies["sesion"]])


async def test_los_errores_de_bd_no_incluyen_los_parametros(sesion_bd):
    """Un INSERT que falla no copia el hash ni los valores al mensaje de la excepción."""
    from sqlalchemy.exc import IntegrityError

    from app.models import Usuario

    nombre = f"d_{uuid.uuid4().hex[:10]}"
    marca = "marca-secreta-del-hash"
    sesion_bd.add(Usuario(usuario=nombre, hash_password=marca, rol="cliente"))
    await sesion_bd.commit()
    sesion_bd.add(Usuario(usuario=nombre, hash_password=marca, rol="cliente"))
    with pytest.raises(IntegrityError) as excepcion:
        await sesion_bd.commit()
    await sesion_bd.rollback()
    assert marca not in str(excepcion.value)
    assert "[parameters:" not in str(excepcion.value)
