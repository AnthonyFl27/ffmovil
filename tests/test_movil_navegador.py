"""T-104: prueba de viewport móvil con navegador (CA-07, RNF-12).

Levanta la app real con uvicorn en el event loop de pytest (esquema `test` y
simulador de VentasFF, igual que la fixture `api`), entra como cliente y como
admin en Chromium con viewport 360 × 740 y táctil, recorre cada pantalla y
comprueba que el documento no se desborda y que todo control interactivo mide
al menos 44 px de lado. Se omite con aviso si Playwright o Chromium no están
instalados (`uv run playwright install chromium`).
"""

import asyncio
from decimal import Decimal

import pytest

from app.services import alertas, auditoria, ledger
from app.services.codigos import codigo_pedido
from tests.utilidades import crear_pedido
from tests.utilidades_api import CLAVE, crear_usuario_con_clave
from tests.utilidades_web import cliente_web

playwright_async = pytest.importorskip(
    "playwright.async_api", reason="Playwright no está instalado: se omite la prueba móvil"
)

VIEWPORT = {"width": 360, "height": 740}
LADO_MINIMO = 44

# Devuelve el ancho del documento frente al del viewport y los controles chicos.
# Una casilla u opción dentro de su etiqueta se mide por la etiqueta (es el área táctil).
MEDIR = """
() => {
  const doc = document.documentElement;
  const selector = 'a[href], button, input:not([type=hidden]), select, textarea, summary,'
    + ' [role=button], label:has(input[type=radio]), label:has(input[type=checkbox])';
  const chicos = [];
  for (const el of document.querySelectorAll(selector)) {
    if (!el.checkVisibility({opacityProperty: true, visibilityProperty: true})) continue;
    if ((el.type === 'radio' || el.type === 'checkbox') && el.closest('label')) continue;
    const r = el.getBoundingClientRect();
    if (r.width === 0 && r.height === 0) continue;
    if (r.width < LADO || r.height < LADO) {
      const texto = (el.textContent || el.name || '').trim().slice(0, 30);
      chicos.push(`<${el.tagName.toLowerCase()}> "${texto}" ${Math.round(r.width)}x${Math.round(r.height)}`);
    }
  }
  return {documento: doc.scrollWidth, viewport: doc.clientWidth, chicos};
}
""".replace("LADO", str(LADO_MINIMO))


@pytest.fixture
async def servidor_web(api):
    """URL base de la app servida por uvicorn con el estado que deja la fixture `api`."""
    import uvicorn

    from app.main import app

    config = uvicorn.Config(app, host="127.0.0.1", port=0, lifespan="off", log_level="warning")
    servidor = uvicorn.Server(config)
    tarea = asyncio.create_task(servidor.serve())
    while not servidor.started:
        if tarea.done():
            tarea.result()  # propaga el error de arranque
        await asyncio.sleep(0.05)
    puerto = servidor.servers[0].sockets[0].getsockname()[1]
    yield f"http://127.0.0.1:{puerto}"
    servidor.should_exit = True
    await tarea


@pytest.fixture
async def navegador():
    async with playwright_async.async_playwright() as p:
        try:
            chromium = await p.chromium.launch()
        except playwright_async.Error as error:
            if "Executable doesn't exist" not in str(error):
                raise
            pytest.skip("Chromium no está instalado (uv run playwright install chromium)")
        yield chromium
        await chromium.close()


async def nueva_pagina(navegador):
    contexto = await navegador.new_context(viewport=VIEWPORT, has_touch=True, is_mobile=True)
    pagina = await contexto.new_page()
    # RNF-14: Chromium avisa por consola de cada recurso que la CSP bloquea.
    pagina.violaciones_csp = []
    pagina.on(
        "console",
        lambda m: (
            pagina.violaciones_csp.append(m.text) if "Content Security Policy" in m.text else None
        ),
    )
    return pagina


async def entrar(pagina, base: str, usuario: str, destino: str) -> None:
    await pagina.goto(f"{base}/login")
    await pagina.fill("input[name=usuario]", usuario)
    await pagina.fill("input[name=clave]", CLAVE)
    await pagina.click("button[type=submit]")
    await pagina.wait_for_url(f"{base}{destino}")


async def medir(pagina, nombre: str, problemas: list[str]) -> None:
    """Mide la pantalla, y otra vez con el menú plegable abierto si lo hay."""
    await pagina.wait_for_load_state("networkidle")
    await registrar(pagina, nombre, problemas)
    menu = pagina.locator(".menu-plegable summary")
    if await menu.is_visible():
        await menu.click()
        await pagina.locator(".menu-plegable details[open] ul a").first.wait_for()
        await pagina.wait_for_timeout(300)  # transición de Pico
        await registrar(pagina, f"{nombre} (menú abierto)", problemas)
        await menu.click()  # lo cierra para seguir usando la pantalla
        await pagina.locator(".menu-plegable details[open]").wait_for(state="detached")


async def registrar(pagina, etiqueta: str, problemas: list[str]) -> None:
    r = await pagina.evaluate(MEDIR)
    if r["documento"] > r["viewport"]:
        problemas.append(f"{etiqueta}: el documento mide {r['documento']} px de ancho")
    problemas.extend(f"{etiqueta}: control chico {c}" for c in r["chicos"])


async def recorrer(pagina, base: str, rutas: list[str], problemas: list[str]) -> None:
    for ruta in rutas:
        respuesta = await pagina.goto(f"{base}{ruta}")
        assert respuesta.status == 200, ruta
        await medir(pagina, ruta, problemas)


async def test_pantallas_en_viewport_movil(servidor_web, navegador, api, sesion_bd, simulador):
    base = servidor_web
    # Cliente con saldo, abono, paquete y pedidos en cada estado final.
    _, cliente, paquete = await cliente_web(api, sesion_bd, simulador)
    admin = await crear_usuario_con_clave(sesion_bd, rol="admin")
    archivado = await crear_usuario_con_clave(sesion_bd, activo=False)
    archivado.archivado = True  # RF-60: su ficha y el listado de archivados
    await ledger.reservar(sesion_bd, cliente.id, Decimal("0.75"))
    pedidos = [
        await crear_pedido(sesion_bd, cliente.id, paquete, estado=estado, referencia=referencia)
        for estado, referencia in (
            ("EXITOSO", "EV-MOVIL0001"),
            ("FALLIDO", None),
            ("PENDIENTE_VERIFICAR", None),
        )
    ]
    for pedido in pedidos:
        pedido.codigo = codigo_pedido(pedido.id)
    await alertas.registrar_alerta(sesion_bd, "cuenta", "Alerta de la prueba móvil")
    auditoria.registrar(sesion_bd, admin.id, "prueba.movil", {"detalle": "móvil"}, "203.0.113.9")
    await sesion_bd.commit()
    exitoso, _, pendiente = pedidos
    problemas: list[str] = []

    pagina = await nueva_pagina(navegador)
    paginas = [pagina]
    await pagina.goto(f"{base}/login")
    await medir(pagina, "/login", problemas)
    await entrar(pagina, base, cliente.usuario, "/inicio")
    await recorrer(
        pagina,
        base,
        ["/inicio", "/recargar", "/historial", f"/historial/{exitoso.codigo}", "/fondos", "/clave"],
        problemas,
    )
    # Pasos 2 y 3 de la recarga con validador no disponible: tarjeta con aviso,
    # paquetes y resumen con la casilla obligatoria (CHG-010).
    simulador.escenario_validar = "no_disponible"
    await pagina.goto(f"{base}/recargar")
    # Player ID vacío: etiqueta roja bajo el campo, sin desbordar (RF-27).
    await pagina.click("form[hx-post='/recargar/validar'] button[type=submit]")
    await pagina.locator("#mensaje-id .mensaje.error").wait_for()
    await medir(pagina, "/recargar (etiqueta de ID vacío)", problemas)
    await pagina.fill("input[name=player_id]", "75807448")
    await pagina.click("form[hx-post='/recargar/validar'] button[type=submit]")
    await pagina.locator("article.jugador").wait_for()
    await medir(pagina, "/recargar (jugador y paquetes)", problemas)
    await pagina.locator("input[name=paquete_id]").first.check()
    await pagina.locator("input[name=confirmar_sin_verificar]").wait_for()
    await medir(pagina, "/recargar (resumen)", problemas)
    # Filtros desplegados del historial.
    await pagina.goto(f"{base}/historial")
    await pagina.click("details.filtros > summary")
    await medir(pagina, "/historial (filtros abiertos)", problemas)

    pagina = await nueva_pagina(navegador)
    paginas.append(pagina)
    await entrar(pagina, base, admin.usuario, "/gestion")
    await recorrer(
        pagina,
        base,
        [
            "/gestion",
            f"/gestion/pedidos?usuario={cliente.usuario}",
            f"/gestion/pedidos/{pendiente.id}",
            "/gestion/usuarios",
            f"/gestion/usuarios/{cliente.id}",
            "/gestion/usuarios?archivados=1",
            f"/gestion/usuarios/{archivado.id}",
            "/gestion/paquetes",
            "/gestion/auditoria",
            "/gestion/updates",
        ],
        problemas,
    )

    # Ficha del cliente con el historial de movimientos y sus filtros abiertos (RF-43).
    await pagina.goto(f"{base}/gestion/usuarios/{cliente.id}")
    await pagina.click("details.filtros > summary")
    await medir(pagina, "/gestion/usuarios/{id} (filtros abiertos)", problemas)

    # Listado de usuarios: filtros de RF-61 a 360 px y búsqueda en vivo.
    await pagina.goto(f"{base}/gestion/usuarios")
    await pagina.click("details.filtros > summary")
    await medir(pagina, "/gestion/usuarios (filtros abiertos)", problemas)
    await pagina.fill("input[name=q]", cliente.usuario)
    await pagina.wait_for_url(lambda url: f"q={cliente.usuario}" in url)
    await pagina.wait_for_load_state("networkidle")
    assert await pagina.locator("#tabla-usuarios tbody tr").count() == 1

    assert not problemas, "Problemas a 360 × 740:\n" + "\n".join(problemas)
    violaciones = [v for p in paginas for v in p.violaciones_csp]
    assert not violaciones, "Violaciones de la CSP (RNF-14):\n" + "\n".join(violaciones)


async def test_recarga_en_tres_pasos(servidor_web, navegador, api, sesion_bd, simulador):
    # Paso 1 solo el Player ID; paso 2 tarjeta del jugador y paquetes, sin "Verificar ID";
    # paso 3 resumen a la vista al tocar un paquete; al confirmar queda solo el pedido
    # (RF-20, RF-21; CHG-010).
    base = servidor_web
    _, cliente, paquete = await cliente_web(api, sesion_bd, simulador)
    pagina = await nueva_pagina(navegador)
    await entrar(pagina, base, cliente.usuario, "/inicio")
    await pagina.goto(f"{base}/recargar")
    assert await pagina.locator("input[name=paquete_id]").count() == 0
    await pagina.fill("input[name=player_id]", "75807448")
    await pagina.click("form[hx-post='/recargar/validar'] button[type=submit]")

    tarjeta = pagina.locator("article.jugador")
    await playwright_async.expect(tarjeta).to_contain_text("Nombre de usuario: Jugador7448")
    await playwright_async.expect(tarjeta).to_contain_text("ID de jugador: 75807448")
    await playwright_async.expect(pagina.get_by_role("button", name="Verificar ID")).to_have_count(
        0
    )

    await pagina.check(f"input[name=paquete_id][value='{paquete.paquete_id}']")
    titulo = pagina.get_by_role("heading", name="Confirma la recarga")
    await playwright_async.expect(titulo).to_be_in_viewport()

    await pagina.click("form[hx-post='/recargar/confirmar'] button[type=submit]")
    await pagina.locator("#recarga article[id^=pedido-]").wait_for()
    await playwright_async.expect(tarjeta).to_have_count(0)
    await playwright_async.expect(pagina.locator("input[name=paquete_id]")).to_have_count(0)
    await pagina.get_by_role("button", name="Nueva recarga").click()
    await pagina.wait_for_url(f"{base}/recargar")
    assert await pagina.input_value("input[name=player_id]") == ""
    assert not pagina.violaciones_csp, "\n".join(pagina.violaciones_csp)


# --- T-124: página pública y legales (CA-07, CA-10, RNF-12, RNF-14, RNF-20) ----------

ESTADO_REVELAR = """
() => [...document.querySelectorAll('.revelar')].map(el => {
  const estilo = getComputedStyle(el);
  return {visible: el.classList.contains('visible'), opacidad: estilo.opacity,
          transformacion: estilo.transform};
})
"""


async def desplazar_hasta_el_final(pagina) -> None:
    """Baja de a poco para que el `IntersectionObserver` vea cada sección."""
    while await pagina.evaluate(
        "() => window.scrollY + window.innerHeight < document.documentElement.scrollHeight - 2"
    ):
        await pagina.mouse.wheel(0, 300)
        await pagina.wait_for_timeout(120)
    await pagina.wait_for_timeout(700)  # fin de las transiciones


async def test_pagina_publica_en_viewport_movil(servidor_web, navegador):
    """CA-07, CA-10 y CA-12 en `/`, `/terminos`, `/privacidad` y `/resellers` a 360 × 740, sin violaciones de CSP.

    Botón «Iniciar sesión» visible sin desplazarse; los `.revelar` aparecen al desplazar
    (RF-58 d, RNF-20). El correo del pie se mide también (área táctil).
    """
    from app.config import Revendedor
    from app.main import app

    base = servidor_web
    app.state.correo_contacto = "contacto-de-prueba-largo@ejemplo.test"
    # RF-62: con revendedores aparecen la sección de la portada, el enlace del pie y `/resellers`.
    app.state.revendedores = [
        Revendedor(
            nombre="Revendedor de Prueba con un Nombre Largo",
            whatsapp="50500000001",
            telegram="prueba_telegram",
            foto="revendedor-1.webp",
        ),
        Revendedor(nombre="Revendedor Solo Web", web="https://www.ejemplo-de-prueba.test/"),
    ]
    problemas: list[str] = []
    try:
        pagina = await nueva_pagina(navegador)
        await pagina.goto(f"{base}/")
        await pagina.wait_for_load_state("networkidle")
        boton = pagina.locator(".cabecera a[href='/login']")
        await playwright_async.expect(boton).to_have_text("Iniciar sesión")
        await playwright_async.expect(boton).to_be_in_viewport()
        antes = await pagina.evaluate(ESTADO_REVELAR)
        assert antes and not all(e["visible"] for e in antes)  # hay secciones bajo el pliegue
        await desplazar_hasta_el_final(pagina)
        despues = await pagina.evaluate(ESTADO_REVELAR)
        assert all(e["visible"] and e["opacidad"] == "1" for e in despues), despues
        await medir(pagina, "/", problemas)
        for ruta in ("/terminos", "/privacidad", "/resellers"):
            await pagina.goto(f"{base}{ruta}")
            await playwright_async.expect(boton).to_be_in_viewport()
            await medir(pagina, ruta, problemas)
    finally:
        app.state.correo_contacto = ""
        app.state.revendedores = []
    assert not problemas, "Problemas a 360 × 740:\n" + "\n".join(problemas)
    assert not pagina.violaciones_csp, "\n".join(pagina.violaciones_csp)


async def test_pagina_publica_sin_movimiento_ni_javascript(servidor_web, navegador):
    """RNF-20: con `prefers-reduced-motion` todo se ve sin animar; sin JavaScript, también."""
    base = servidor_web
    for opciones in ({"reduced_motion": "reduce"}, {"java_script_enabled": False}):
        contexto = await navegador.new_context(viewport=VIEWPORT, **opciones)
        pagina = await contexto.new_page()
        await pagina.goto(f"{base}/")
        await pagina.wait_for_load_state("networkidle")
        estados = await pagina.evaluate(ESTADO_REVELAR)
        assert estados, opciones
        for estado in estados:
            assert (estado["opacidad"], estado["transformacion"]) == ("1", "none"), opciones
        if "reduced_motion" in opciones:  # los diamantes tampoco flotan
            animaciones = await pagina.evaluate(
                "() => [...document.querySelectorAll('.flotar')]"
                ".map(el => getComputedStyle(el).animationName)"
            )
            assert animaciones and set(animaciones) == {"none"}
        await contexto.close()


async def test_filtros_plegados_tambien_en_escritorio(api, sesion_bd, servidor_web, navegador):
    """RNF-12, RF-61: ningún listado arranca con «Filtros» desplegado, ni en escritorio."""
    admin = await crear_usuario_con_clave(sesion_bd, rol="admin")
    contexto = await navegador.new_context(viewport={"width": 1280, "height": 800})
    pagina = await contexto.new_page()
    await entrar(pagina, servidor_web, admin.usuario, "/gestion")
    for ruta in ("/gestion/pedidos", "/gestion/usuarios", "/gestion/auditoria"):
        await pagina.goto(f"{servidor_web}{ruta}")
        await pagina.wait_for_load_state("networkidle")
        assert await pagina.locator("details.filtros").count() == 1, ruta
        assert not await pagina.locator("details.filtros").evaluate("d => d.open"), ruta
        # Se despliega al tocar «Filtros».
        await pagina.click("details.filtros > summary")
        assert await pagina.locator("details.filtros").evaluate("d => d.open"), ruta
    await contexto.close()
