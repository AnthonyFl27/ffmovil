"""T-122 y T-123: página pública `/` y páginas legales (RF-58, RF-59, CA-10, CHG-021).

Contenido de RF-58, sin precios ni importes, sin código en línea ni recursos de otros
dominios (RNF-14, RNF-20), correo opcional, redirecciones con sesión (RF-02), tope
anónimo (RNF-17) y ninguna lectura de paquetes, saldos o pedidos ni llamada a VentasFF.
"""

import re
from contextlib import contextmanager
from datetime import UTC, datetime

import pytest
from sqlalchemy import event

from app.main import app
from tests.utilidades_api import CLAVE, crear_usuario_con_clave, iniciar_sesion
from tests.utilidades_web import htmx_post

PUBLICAS = ("/", "/terminos", "/privacidad")
LEGALES = ("/terminos", "/privacidad")
TITULOS = {"/terminos": "Términos y Condiciones", "/privacidad": "Política de Privacidad"}
TEXTO_PORTADA = (
    "Ya puedes vender diamantes a tus propios clientes usando nuestros precios "
    "y nuestra plataforma."
)
AVISO_MARCAS = (
    "Free Fire y Garena son marcas registradas de sus titulares. "
    "Este sitio no está patrocinado ni avalado por Garena."
)
CORREO = "contacto@ejemplo.test"


class SinVentasFF:
    """Sustituto del cliente VentasFF: cualquier uso hace fallar la prueba."""

    def __getattr__(self, nombre):
        raise AssertionError(f"La página pública usó VentasFF ({nombre})")


@contextmanager
def consultas_sql(motor):
    """Registra el SQL que ejecuta la app mientras dura el bloque."""
    registradas: list[str] = []

    def anotar(conn, cursor, sentencia, *args):
        registradas.append(sentencia.lower())

    event.listen(motor.sync_engine, "before_cursor_execute", anotar)
    try:
        yield registradas
    finally:
        event.remove(motor.sync_engine, "before_cursor_execute", anotar)


@pytest.fixture
def correo():
    app.state.correo_contacto = CORREO
    yield CORREO
    app.state.correo_contacto = ""


def _pie_completo(html: str) -> None:
    assert 'href="/terminos"' in html and "Términos y Condiciones" in html
    assert 'href="/privacidad"' in html and "Política de Privacidad" in html
    assert f"© {datetime.now(UTC).year} FFMovil • Todos los derechos reservados" in html
    assert AVISO_MARCAS in html
    assert 'alt="Protected by Cloudflare"' in html
    assert 'href="https://www.cloudflare.com/"' in html


# --- T-122: página `/` (RF-58, CA-10) ------------------------------------------------


async def test_sin_sesion_muestra_la_presentacion(api):
    """RF-58 (a) a (e) y CA-10: botón a /login, portada, tres pasos y pie completo."""
    r = await api().get("/", follow_redirects=False)
    assert r.status_code == 200
    html = r.text
    assert html.count('href="/login"') >= 2  # encabezado y portada
    assert "Iniciar sesión" in html and "FFMovil" in html
    assert TEXTO_PORTADA in html
    assert "inicio/diamantes.webp" in html and "inicio/cofre.webp" in html
    assert len(re.findall(r'class="paso[ "]', html)) == 3
    for paso in ("Recibe tu cuenta", "Ten saldo abonado", "Recarga con el Player ID"):
        assert paso in html
    assert html.count("inicio/personaje-") == 2 and "revelar" in html
    _pie_completo(html)


@pytest.mark.parametrize("ruta", PUBLICAS)
async def test_sin_precios_importes_ni_extras_del_pie(api, ruta):
    """RF-58: sin precios ni importes; el pie, sin idioma, moneda, ayuda ni WhatsApp.

    En `/` se revisa toda la página; en las legales solo el pie, porque su texto (del
    dueño, RF-59) menciona la moneda y el WhatsApp próximo.
    """
    html = (await api().get(ruta)).text
    if ruta != "/":
        html = html[html.index("<footer") :]
    visible = re.sub(r"<[^>]+>", " ", html).lower()
    assert not re.search(r"\d+[.,]\d{2}\b", visible)
    for prohibido in ("usd", "$", "precio:", "saldo disponible", "whatsapp", "idioma", "ayuda"):
        assert prohibido not in visible, prohibido
    assert "moneda" not in visible


@pytest.mark.parametrize("ruta", PUBLICAS)
async def test_sin_codigo_en_linea_ni_recursos_externos(api, ruta):
    """RNF-14 y RNF-20: sin `style=`, `<script>` en línea, `hx-on` ni recursos de otros dominios."""
    html = (await api().get(ruta)).text
    assert "style=" not in html and "<style" not in html and "hx-on" not in html
    for apertura, cuerpo in re.findall(r"(<script\b[^>]*>)(.*?)</script>", html, re.DOTALL):
        assert 'src="/static/' in apertura and cuerpo.strip() == ""
    for etiqueta in re.findall(r"<(?:img|script|link)\b[^>]*>", html):
        for url in re.findall(r'(?:src|href)="([^"]+)"', etiqueta):
            assert url.startswith("/static/"), etiqueta
    # Las páginas públicas no cargan Pico.css, HTMX ni el CSRF (plan sec. 6.3).
    assert "pico.min.css" not in html and "htmx" not in html and "X-CSRF-Token" not in html
    assert "<form" not in html


async def test_el_correo_solo_aparece_si_esta_definido(api, correo):
    """RF-58 (e): el correo de `CONTACT_EMAIL` se muestra; sin valor, no hay línea de contacto."""
    html = (await api().get("/")).text
    assert f'href="mailto:{correo}"' in html and "Contacto" in html
    app.state.correo_contacto = ""
    html = (await api().get("/")).text
    assert "mailto:" not in html and ">Contacto<" not in html


async def test_con_sesion_sigue_redirigiendo(api, sesion_bd):
    """RF-58 y RF-02: cliente, admin y cambio de clave pendiente no ven la presentación."""
    casos = (
        ({"rol": "cliente"}, "/inicio"),
        ({"rol": "admin"}, "/gestion"),
        ({"debe_cambiar_clave": True}, "/clave"),
    )
    for datos, destino in casos:
        usuario = await crear_usuario_con_clave(sesion_bd, **datos)
        http = api()
        await htmx_post(http, "/login", {"usuario": usuario.usuario, "clave": CLAVE})
        r = await http.get("/", follow_redirects=False)
        assert (r.status_code, r.headers["location"]) == (303, destino)


async def test_la_ruta_publica_cuenta_en_el_tope_anonimo(api, simulador):
    """RNF-17: `/`, `/terminos` y `/privacidad` cuentan en el tope por IP."""
    from app.services.limitador import LimitadorPorUsuario

    app.state.limitador_anonimo = LimitadorPorUsuario(3)
    http = api("203.0.113.40")
    for ruta in PUBLICAS:
        assert (await http.get(ruta)).status_code == 200
    r = await http.get("/")
    assert r.status_code == 429 and "Demasiadas peticiones" in r.text
    assert (await http.get("/terminos")).status_code == 429


# --- T-123: páginas legales (RF-59, CA-10) -------------------------------------------


@pytest.mark.parametrize("ruta", LEGALES)
async def test_legales_sin_sesion(api, ruta, correo):
    """RF-59: 200 sin sesión, mismo encabezado y pie, enlace de vuelta y contacto."""
    r = await api().get(ruta, follow_redirects=False)
    assert r.status_code == 200
    html = r.text
    assert f"<h1>{TITULOS[ruta]}</h1>" in html
    assert 'class="volver"' in html and 'href="/"' in html
    assert 'href="/login"' in html and 'class="cabecera"' in html
    assert html.count(f'href="mailto:{correo}"') >= 2  # en el texto y en el pie
    _pie_completo(html)


async def test_legales_describen_el_servicio(api):
    """RF-59 (CHG-023): texto del dueño, ajustado a la spec en lo que dice de la plataforma."""
    terminos = (await api().get("/terminos")).text
    for frase in (
        "prepago",
        "Player ID",
        "En revisión",
        "9. Clientes menores de edad",
        "consentimiento de su padre, madre o tutor legal",
        "11. Política de reembolsos",
        "16. Ley aplicable",
    ):
        assert frase in terminos, frase
    assert "otras monedas" not in terminos  # la app solo muestra USD (RF-36)
    privacidad = (await api().get("/privacidad")).text
    for frase in (
        "contraseña",
        "dirección IP",
        "Player ID",
        "8. Cookies",
        "registro contable",
        "tutor legal",
    ):
        assert frase in privacidad, frase
    # Solo hay cookie de sesión: el CSRF no usa cookie (RF-04).
    assert "una cookie técnica, necesaria para mantener tu sesión iniciada" in privacidad
    assert "formularios" not in privacidad


@pytest.mark.parametrize("plantilla", ["terminos.html", "privacidad.html"])
def test_el_correo_no_esta_escrito_en_las_plantillas(plantilla):
    """RF-59 y RNF-06: el correo sale de `CONTACT_EMAIL`, no del texto."""
    from app.web.plantillas import DIRECTORIO_PLANTILLAS

    texto = (DIRECTORIO_PLANTILLAS / "publica" / plantilla).read_text()
    assert "@" not in texto and "{{ correo }}" in texto


async def test_sin_correo_las_legales_omiten_esa_linea(api):
    """RF-59: sin `CONTACT_EMAIL` no queda una línea de correo vacía."""
    for ruta in LEGALES:
        html = (await api().get(ruta)).text
        assert "mailto:" not in html and "Correo:" not in html


@pytest.mark.parametrize("ruta", LEGALES)
async def test_legales_con_sesion_no_redirigen(api, sesion_bd, ruta):
    """RF-59 y CA-10: con sesión (cliente o con cambio pendiente) también responden 200."""
    for datos in ({"rol": "cliente"}, {"rol": "admin"}, {"debe_cambiar_clave": True}):
        usuario = await crear_usuario_con_clave(sesion_bd, **datos)
        http = api()
        await iniciar_sesion(http, usuario.usuario)
        assert (await http.get(ruta, follow_redirects=False)).status_code == 200


# --- CA-10: ninguna de las tres usa VentasFF ni lee paquetes, saldos o pedidos -------


async def test_no_leen_datos_del_negocio_ni_llaman_a_ventasff(api, sesion_bd, motor_bd):
    """CA-10 y RF-58: solo se consulta la sesión; nada de paquetes, saldos ni pedidos."""
    usuario = await crear_usuario_con_clave(sesion_bd, "cliente")
    con_sesion = api()
    await iniciar_sesion(con_sesion, usuario.usuario)
    sin_sesion = api()
    real = app.state.ventasff
    app.state.ventasff = SinVentasFF()
    try:
        with consultas_sql(motor_bd) as sql:
            for ruta in PUBLICAS:
                assert (await sin_sesion.get(ruta)).status_code == 200
            for ruta in LEGALES:
                assert (await con_sesion.get(ruta)).status_code == 200
    finally:
        app.state.ventasff = real
    for tabla in ("paquetes", "saldos", "pedidos", "movimientos"):
        assert not [s for s in sql if re.search(rf"\b{tabla}\b", s)], tabla
