"""T-122, T-123 y T-131 a T-133: página pública, legales y `/resellers` (RF-58, RF-59, RF-62, CA-10, CA-12).

Contenido de RF-58, sin precios ni importes, sin código en línea ni recursos de otros
dominios (RNF-14, RNF-20), correo opcional, redirecciones con sesión (RF-02), tope
anónimo (RNF-17) y ninguna lectura de paquetes, saldos o pedidos ni llamada a VentasFF.
"""

import re
from contextlib import contextmanager
from datetime import UTC, datetime

import pytest
from sqlalchemy import event

from app.config import ErrorConfiguracion, Revendedor
from app.main import app
from app.web.publica import verificar_archivos_revendedores
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
    "La marca Free Fire es propiedad exclusiva de Garena. Este sitio opera de manera independiente."
)
CORREO = "contacto@ejemplo.test"


def _texto(html: str) -> str:
    """Texto visible: sin etiquetas (el título lleva `<em>`) y con los espacios normalizados."""
    return " ".join(re.sub(r"<[^>]+>", " ", html).split())


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
    assert f"© {datetime.now(UTC).year} FFmovil • Todos los derechos reservados" in html
    assert AVISO_MARCAS in html
    assert 'alt="Protected by Cloudflare"' in html
    assert 'href="https://www.cloudflare.com/"' in html


# --- T-122: página `/` (RF-58, CA-10) ------------------------------------------------


async def test_sin_sesion_muestra_la_presentacion(api):
    """RF-58 (a) a (e) y CA-10: botón a /login (solo en el encabezado), tarjeta, diamante, tres pasos y pie."""
    r = await api().get("/", follow_redirects=False)
    assert r.status_code == 200
    html = r.text
    assert html.count('href="/login"') == 1  # solo el botón del encabezado
    assert "Iniciar sesión" in html and "FFmovil" in html
    assert TEXTO_PORTADA in _texto(html)
    assert "inicio/personaje-2.webp" in html and "inicio/diamantes.webp" in html
    assert len(re.findall(r'class="paso[ "]', html)) == 3
    for paso in ("Recibe tu cuenta", "Ten saldo abonado", "Recarga con el Player ID"):
        assert paso in html
    # CHG-035: las secciones de personajes 1 y 3, la franja de armas y las fotos de los pasos se retiraron.
    for imagen in ("personaje-1", "personaje-3", "arma-1", "arma-2", "cofre", "maletin"):
        assert f"inicio/{imagen}.webp" not in html, imagen
    assert "revelar" in html
    _pie_completo(html)


async def test_la_portada_tiene_tarjeta_diamante_notas_y_divisores(api):
    """RF-58 (b) a (d), CHG-035: tarjeta con apoyo, sección del diamante con sus notas y divisores."""
    html = (await api().get("/")).text
    assert 'class="tarjeta portada-tarjeta"' in html and 'id="fondo-ascii"' in html
    assert (
        "Cuenta prepago, recarga con el Player ID y tus pedidos siempre a la vista, desde el celular."
        in html
    )
    assert "Diamantes de Free Fire, sin complicaciones" in html
    assert "Una plataforma prepago pensada para quien vende recargas todos los días." in html
    assert 'id="diamante"' in html and 'aria-hidden="true"' in html
    assert "<b>Recarga con Player ID</b>Comprueba el nombre del jugador antes de confirmar." in html
    assert "<b>Saldo prepago</b>Recargas con el saldo que te abona nuestro equipo." in html
    # Divisores: tras la tarjeta, tras el diamante y al final del contenido.
    assert html.count('class="divisor"') == 3
    assert '<main class="marco">' in html
    # Los canvas son solo decoración: el JavaScript propio se carga de /static, solo en la portada.
    assert "/static/portada.js" in html
    for ruta in ("/terminos", "/privacidad"):
        assert "portada.js" not in (await api().get(ruta)).text, ruta


@pytest.mark.parametrize("ruta", ["/terminos", "/privacidad"])
async def test_las_legales_usan_el_tema_de_la_portada(api, ruta):
    """RF-59, CHG-035: tarjeta de título con el enlace de vuelta, divisores y el mismo marco."""
    html = (await api().get(ruta)).text
    assert 'class="tarjeta tarjeta-pagina"' in html and '<main class="marco">' in html
    assert html.index('class="volver"') < html.index("<h1>") < html.index('class="divisor"')
    assert html.count('class="divisor"') == 2


async def test_la_portada_lleva_el_personaje_con_el_diamante_y_no_repite_el_boton(api):
    """RF-58 (b), CHG-024: el botón queda solo en el encabezado; personaje y diamante."""
    html = (await api().get("/")).text
    portada = html[html.index('<section class="portada">') : html.index("</section>")]
    assert TEXTO_PORTADA in _texto(portada)
    assert "/login" not in portada
    assert "inicio/personaje-2.webp" in portada and "inicio/diamantes.webp" in portada
    assert 'class="flotar"' in portada and "inicio/cofre.webp" not in portada
    assert "Cuenta prepago, recarga con el Player ID" in portada
    cabecera = html[html.index('<header class="cabecera">') : html.index("</header>")]
    assert 'href="/login"' in cabecera


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


# --- T-131 a T-133: contacto de revendedores (RF-62, RF-58, RF-59, CA-12) --------------

COMPLETO = Revendedor(
    nombre="Ana Prueba",
    whatsapp="50500000001",
    telegram="ana_prueba",
    foto="revendedor-1.webp",
)
SOLO_WHATSAPP = Revendedor(nombre="Luis Prueba", whatsapp="50500000002")
SOLO_WEB = Revendedor(nombre="Marta Web", web="https://www.ejemplo-web.test/tienda")
MENSAJE_URL = "Hola%2C%20quiero%20abrir%20mi%20usuario%20en%20FFmovil."


@pytest.fixture
def revendedores():
    app.state.revendedores = [COMPLETO, SOLO_WHATSAPP]
    yield app.state.revendedores
    app.state.revendedores = []


async def test_resellers_muestra_foto_nombre_y_canales(api, revendedores):
    """RF-62 y CA-12: foto o inicial, nombre y enlaces wa.me (con mensaje) y t.me."""
    r = await api().get("/resellers", follow_redirects=False)
    assert r.status_code == 200
    html = r.text
    assert 'class="tarjeta tarjeta-pagina"' in html and 'class="divisor"' in html  # CHG-035
    assert 'href="/"' in html and "Volver al inicio" in html  # enlace de vuelta
    ana, luis = html.split('<li class="revendedor">')[1:]
    assert "Ana Prueba" in ana and "revendedor-1.webp" in ana  # con foto
    assert f'href="https://wa.me/50500000001?text={MENSAJE_URL}"' in ana
    assert 'href="https://t.me/ana_prueba"' in ana
    assert "QR" not in html  # el QR se retiró (CHG-032)
    assert 'rel="noopener noreferrer"' in ana and 'target="_blank"' in ana
    # Sin foto: la inicial; solo los canales definidos.
    assert "Luis Prueba" in luis and "revendedor-foto" not in luis and ">L<" in luis
    assert "wa.me/50500000002" in luis
    assert "t.me" not in luis


async def test_resellers_muestra_el_boton_sitio_web(api, revendedores):
    """RF-62 y CA-12 (CHG-034): «Sitio web» solo con `web`, en pestaña nueva y sin Telegram."""
    app.state.revendedores = [COMPLETO, SOLO_WEB]
    html = (await api().get("/resellers")).text
    ana, marta = html.split('<li class="revendedor">')[1:]
    assert "Sitio web" not in ana and "web.webp" not in ana  # Ana no tiene web
    assert "Marta Web" in marta and ">M<" in marta  # sin foto: la inicial
    assert (
        '<a class="canal canal-web" href="https://www.ejemplo-web.test/tienda" '
        'target="_blank" rel="noopener noreferrer">'
    ) in marta
    assert "Sitio web</a>" in marta and "web.webp" in marta
    assert "wa.me" not in marta and "t.me" not in marta  # solo los canales definidos


async def test_resellers_foto_con_prefijo_logo_se_muestra_como_logo(api, revendedores):
    """RF-62: `foto` que empieza por `logo-` va como logo sin recorte circular (CHG-034)."""
    app.state.revendedores = [
        COMPLETO,
        Revendedor(nombre="Negocio Web", whatsapp="50500000003", foto="logo-centerunlock.webp"),
    ]
    html = (await api().get("/resellers")).text
    ana, negocio = html.split('<li class="revendedor">')[1:]
    assert "revendedor-foto" in ana and "revendedor-logo" not in ana
    assert 'class="revendedor-logo"' in negocio and "revendedor-foto" not in negocio
    assert 'alt="Logo de Negocio Web"' in negocio and "logo-centerunlock.webp" in negocio


async def test_resellers_sin_revendedores_es_404_y_no_hay_enlaces(api):
    """RF-62 y CA-12: sin `RESELLERS`, `/resellers` da 404 y la portada y el pie no lo muestran."""
    assert (await api().get("/resellers")).status_code == 404
    html = (await api().get("/")).text
    assert "/resellers" not in html and "Aún no tienes usuario" not in html


async def test_portada_y_pie_enlazan_a_resellers(api, revendedores, correo):
    """RF-58 (b) y (e): sección dentro de la tarjeta principal y enlace «Revendedores» bajo el correo del pie."""
    html = (await api().get("/")).text
    portada = html[html.index('<section class="portada">') : html.index("</section>")]
    assert "¿Aún no tienes usuario?" in portada  # dentro de la tarjeta, no más abajo
    assert html.index("¿Aún no tienes usuario?") < html.index("titulo-mundo")
    assert "Contáctate con uno de nuestros revendedores" in html
    assert 'class="boton boton-claro">Ver revendedores</a>' in html
    pie = html[html.index("<footer") :]
    assert pie.index("mailto:") < pie.index('href="/resellers">Revendedores</a>')
    assert "Nuestro equipo crea tu cuenta" in html  # paso 1 (RF-58 c)
    # Sin números ni enlaces de contacto fuera de /resellers.
    assert "wa.me" not in html and "t.me" not in html and "50500000001" not in html


async def test_el_pie_muestra_contacto_solo_con_revendedores_sin_correo(api, revendedores):
    """RF-58 (e): la columna «Contacto» existe si hay correo o revendedores."""
    html = (await api().get("/")).text
    assert ">Contacto<" in html and "mailto:" not in html
    assert 'href="/resellers">Revendedores</a>' in html


async def test_resellers_con_sesion_no_redirige(api, sesion_bd, revendedores):
    """RF-62: con sesión (cliente, admin o cambio pendiente) también responde 200."""
    for datos in ({"rol": "cliente"}, {"rol": "admin"}, {"debe_cambiar_clave": True}):
        usuario = await crear_usuario_con_clave(sesion_bd, **datos)
        http = api()
        await iniciar_sesion(http, usuario.usuario)
        assert (await http.get("/resellers", follow_redirects=False)).status_code == 200


async def test_resellers_sin_codigo_en_linea_ni_recursos_externos(api, revendedores):
    """RNF-14 y RNF-20 en `/resellers`: todo desde /static; solo los enlaces de contacto salen."""
    html = (await api().get("/resellers")).text
    assert "style=" not in html and "<style" not in html and "hx-on" not in html
    assert "<script" not in html.replace('<script src="/static/', "")
    for etiqueta in re.findall(r"<(?:img|script|link)\b[^>]*>", html):
        for url in re.findall(r'(?:src|href)="([^"]+)"', etiqueta):
            assert url.startswith("/static/"), etiqueta


async def test_resellers_cuenta_en_el_tope_anonimo_y_no_usa_datos_del_negocio(
    api, revendedores, motor_bd
):
    """RNF-17 y RF-62: cuenta en el tope por IP, no lee la BD (salvo la sesión) ni llama a VentasFF."""
    from app.services.limitador import LimitadorPorUsuario

    real = app.state.ventasff
    app.state.ventasff = SinVentasFF()
    try:
        with consultas_sql(motor_bd) as sql:
            assert (await api().get("/resellers")).status_code == 200
    finally:
        app.state.ventasff = real
    for tabla in ("paquetes", "saldos", "pedidos", "movimientos"):
        assert not any(tabla in s for s in sql), tabla
    app.state.limitador_anonimo = LimitadorPorUsuario(1)
    http = api("203.0.113.41")
    assert (await http.get("/resellers")).status_code == 200
    assert (await http.get("/resellers")).status_code == 429


def test_la_foto_de_la_configuracion_debe_existir():
    """RF-62: una foto que no existe en `static/inicio/` impide arrancar."""
    verificar_archivos_revendedores([COMPLETO, SOLO_WHATSAPP])
    with pytest.raises(ErrorConfiguracion, match="no-existe.webp"):
        verificar_archivos_revendedores(
            [Revendedor(nombre="X", whatsapp="50500000004", foto="no-existe.webp")]
        )


async def test_legales_mencionan_a_los_revendedores_del_equipo(api, revendedores):
    """RF-59 (CHG-031): las cuentas las crea FFmovil o su equipo; se piden por correo o `/resellers`."""
    terminos = (await api().get("/terminos")).text
    assert "revendedores del equipo de FFmovil" in terminos
    assert "o los <strong>revendedores del equipo de FFmovil</strong> que autorizamos" in terminos
    privacidad = (await api().get("/privacidad")).text
    assert "un revendedor del equipo de FFmovil" in privacidad
    assert "Revendedores del equipo de FFmovil:" in privacidad
    # Sin choque de palabras: el cliente es «cliente revendedor»; «revendedor» a secas es del equipo.
    for frase in ("Si eres <strong>cliente revendedor</strong>", "Como cliente revendedor"):
        assert frase in terminos, frase
    for frase in ("cuenta de cliente revendedor", "nuestros clientes revendedores"):
        assert frase in privacidad, frase
    for html in (terminos, privacidad):
        texto = re.sub(r"<[^>]+>", "", html.split("<footer")[0]).lower()
        sueltos = re.findall(
            r"(?<!cliente )(?<!clientes )\brevendedor(?:es)?\b(?! del equipo)", texto
        )
        assert not sueltos, sueltos
        assert 'href="/resellers"' in html  # solo si hay revendedores definidos
    app.state.revendedores = []
    for ruta in LEGALES:
        assert 'href="/resellers"' not in (await api().get(ruta)).text
